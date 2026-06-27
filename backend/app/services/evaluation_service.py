"""Evaluation service.

Orchestrates the evaluation flow:
  validate request → load adapter → load dataset → generate predictions
  → compute metrics → persist results → return report

Synchronous and simple (MVP). No async workers, no batch, no distributed.

Heavy ML (transformers/peft) imports are LAZY inside methods so the
module imports cleanly in test environments. Tests override
`_generate_predictions` to stub out the model-inference seam.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import UUID

from app.models.evaluation import Evaluation, EvaluationStatus
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.evaluation_repository import EvaluationRepository
from app.repositories.training_job_repository import TrainingJobRepository
from app.schemas.evaluation import (
    EvaluationCreateRequest,
    EvaluationListResponse,
    EvaluationResponse,
)
from app.services import metrics as metrics_module
from app.services.metrics import (
    MetricError,
)


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class EvaluationError(Exception):
    """Base exception for evaluation-related errors."""

    code = "EVALUATION_ERROR"
    http_status = 400


class EvaluationNotFoundError(EvaluationError):
    """Raised when an evaluation does not exist."""

    code = "EVALUATION_NOT_FOUND"
    http_status = 404

    def __init__(self, evaluation_id: UUID) -> None:
        self.evaluation_id = evaluation_id
        super().__init__(f"Evaluation not found: {evaluation_id}")


class EvaluationAccessDeniedError(EvaluationError):
    """Raised when a user accesses an evaluation they do not own."""

    code = "EVALUATION_ACCESS_DENIED"
    http_status = 403

    def __init__(self, evaluation_id: UUID) -> None:
        self.evaluation_id = evaluation_id
        super().__init__(f"Access to evaluation {evaluation_id} is denied.")


class ModelNotFoundError(EvaluationError):
    """Raised when the referenced trained model (training job) is missing."""

    code = "MODEL_NOT_FOUND"
    http_status = 404

    def __init__(self, model_id: UUID) -> None:
        self.model_id = model_id
        super().__init__(f"Trained model not found: {model_id}")


class ModelNotReadyError(EvaluationError):
    """Raised when the referenced training job has no artifact (not completed)."""

    code = "MODEL_NOT_READY"
    http_status = 409

    def __init__(self, model_id: UUID) -> None:
        self.model_id = model_id
        super().__init__(
            f"Trained model {model_id} has no adapter artifact "
            "(training job not completed or no artifact_path)."
        )


class DatasetNotFoundError(EvaluationError):
    """Raised when the referenced dataset is missing or not owned."""

    code = "DATASET_NOT_FOUND"
    http_status = 404

    def __init__(self, dataset_id: UUID) -> None:
        self.dataset_id = dataset_id
        super().__init__(f"Dataset not found or not accessible: {dataset_id}")


class DatasetVersionNotFoundError(EvaluationError):
    """Raised when the referenced dataset version is missing."""

    code = "DATASET_VERSION_NOT_FOUND"
    http_status = 404

    def __init__(self, version_id: UUID) -> None:
        self.version_id = version_id
        super().__init__(f"Dataset version not found: {version_id}")


class AdapterNotFoundError(EvaluationError):
    """Raised when the adapter artifact path does not exist on disk."""

    code = "ADAPTER_NOT_FOUND"
    http_status = 404

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"Adapter artifact not found at path: {path}")


class MetricComputationError(EvaluationError):
    """Raised when metric computation fails."""

    code = "METRIC_COMPUTATION_FAILED"
    http_status = 422

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"Metric computation failed: {detail}")


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class EvaluationService:
    """Business logic for evaluation management."""

    def __init__(
        self,
        evaluation_repo: EvaluationRepository,
        training_job_repo: TrainingJobRepository,
        dataset_repo: DatasetRepository,
    ) -> None:
        self._evals = evaluation_repo
        self._jobs = training_job_repo
        self._datasets = dataset_repo

    # ------------------------------------------------------------------
    # Create + run evaluation
    # ------------------------------------------------------------------

    async def create_evaluation(
        self,
        *,
        user_id: UUID,
        request: EvaluationCreateRequest,
    ) -> EvaluationResponse:
        """Create an evaluation and run it synchronously (MVP).

        Flow:
        1. Validate the trained model (training job) exists, is owned by
           the user, is completed, and has an artifact_path.
        2. Validate the dataset + version exist and are owned by the user.
        3. Create the evaluation row (status=RUNNING).
        4. Load adapter, load dataset records, generate predictions.
        5. Compute metrics (ROUGE-L, BERTScore, semantic similarity).
        6. Persist metrics, set status=COMPLETED.
        7. Return the evaluation response.

        On any failure after row creation, status is set to FAILED with
        an error_message.
        """
        # 1. Validate model (training job)
        job = await self._jobs.get_by_id(request.model_id)
        if job is None or job.user_id != user_id:
            raise ModelNotFoundError(request.model_id)
        if job.artifact_path is None:
            raise ModelNotReadyError(request.model_id)

        # 2. Validate dataset ownership
        dataset = await self._datasets.get_by_id_and_owner(
            request.dataset_id, user_id
        )
        if dataset is None:
            raise DatasetNotFoundError(request.dataset_id)
        # Validate dataset version belongs to this dataset
        version_exists = False
        for v in dataset.versions:
            if v.id == request.dataset_version_id:
                version_exists = True
                break
        if not version_exists:
            raise DatasetVersionNotFoundError(request.dataset_version_id)

        # 3. Create evaluation row
        evaluation = Evaluation(
            user_id=user_id,
            dataset_id=request.dataset_id,
            dataset_version_id=request.dataset_version_id,
            model_id=request.model_id,
            status=EvaluationStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        evaluation = await self._evals.create(evaluation)
        await self._evals.commit()

        # 4-6. Run evaluation; on failure mark FAILED
        try:
            metrics = await self._run_evaluation(
                evaluation_id=evaluation.id,
                artifact_path=job.artifact_path,
                dataset_version_id=request.dataset_version_id,
            )
        except Exception as exc:
            await self._evals.save_error(evaluation.id, str(exc))
            await self._evals.commit()
            # Re-raise metric/adapter errors as-is; wrap unknown errors
            if isinstance(exc, EvaluationError):
                raise
            raise MetricComputationError(str(exc)) from exc

        # 6. Persist metrics + mark completed
        await self._evals.save_metrics(evaluation.id, **metrics)
        await self._evals.update_status(
            evaluation.id,
            EvaluationStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc),
        )
        await self._evals.commit()

        # 7. Return refreshed response
        refreshed = await self._evals.get_by_id(evaluation.id)
        assert refreshed is not None
        return EvaluationResponse.model_validate(refreshed)

    async def _run_evaluation(
        self,
        *,
        evaluation_id: UUID,
        artifact_path: str,
        dataset_version_id: UUID,
    ) -> dict[str, float | None]:
        """Load adapter + dataset, generate predictions, compute metrics.

        Returns a dict with keys: rouge_score, bertscore_precision,
        bertscore_recall, bertscore_f1, semantic_similarity.
        """
        # Validate adapter exists on disk
        if not os.path.isdir(artifact_path):
            raise AdapterNotFoundError(artifact_path)

        # Load dataset records
        records = await self._load_dataset_records(dataset_version_id)
        if not records:
            raise MetricComputationError("dataset version has no records")

        inputs = [r.get("instruction", "") for r in records]
        references = [r.get("response", "") or r.get("output", "") for r in records]

        # Generate predictions (heavy ML seam — tests override this method)
        predictions = await self._generate_predictions(artifact_path, inputs)

        # Compute metrics
        rouge = metrics_module.compute_rouge_l(predictions, references)
        bp, br, bf = metrics_module.compute_bertscore(predictions, references)
        sem = metrics_module.compute_semantic_similarity(predictions, references)

        return {
            "rouge_score": rouge,
            "bertscore_precision": bp,
            "bertscore_recall": br,
            "bertscore_f1": bf,
            "semantic_similarity": sem,
        }

    async def _load_dataset_records(
        self, dataset_version_id: UUID
    ) -> list[dict]:
        """Load records from the dataset version file.

        ponytail: reads the file path from the DatasetVersion row and
        parses CSV/JSON/JSONL. No streaming, no caching — load all into
        memory. Fine for MVP dataset sizes (≤10k records).
        """
        import csv
        import json as json_mod

        from app.models.dataset import DatasetVersion
        from sqlalchemy import select

        result = await self._evals.session.execute(
            select(DatasetVersion).where(DatasetVersion.id == dataset_version_id)
        )
        version = result.scalar_one_or_none()
        if version is None:
            raise DatasetVersionNotFoundError(dataset_version_id)

        file_path = version.file_path
        if not os.path.exists(file_path):
            raise DatasetNotFoundError(dataset_version_id)

        # ponytail: detect format by extension; dataset.format lives on parent
        ext = file_path.rsplit(".", 1)[-1].lower()
        records: list[dict] = []
        if ext == "jsonl":
            with open(file_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json_mod.loads(line))
        elif ext == "json":
            with open(file_path, encoding="utf-8") as f:
                data = json_mod.load(f)
                if isinstance(data, list):
                    records = data
                else:
                    records = [data]
        else:  # csv and friends
            with open(file_path, encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                records = list(reader)
        return records

    async def _generate_predictions(
        self, artifact_path: str, inputs: list[str]
    ) -> list[str]:
        """Load base model + LoRA adapter and generate predictions.

        ponytail: heavy ML imports are lazy. Tests override this method
        to stub out inference. The real implementation loads the adapter
        via transformers + peft and runs model.generate() per input.

        The Phase 4.3 notebook saves the tokenizer to a ``tokenizer/``
        subdirectory inside the adapter dir, so we load it from there.
        The adapter was trained on a 4-bit NF4 quantized base, so the
        base model must be loaded with the same BitsAndBytesConfig —
        loading the base unquantized and then applying the LoRA adapter
        would produce mismatched weights and garbage predictions.
        """
        from app.models.training_job import TrainingJob  # noqa: F401
        from sqlalchemy import select

        # Resolve the training job to get the base_model identifier
        result = await self._evals.session.execute(
            select(TrainingJob).where(TrainingJob.artifact_path == artifact_path)
        )
        job = result.scalar_one_or_none()
        if job is None:
            raise AdapterNotFoundError(artifact_path)

        # Lazy heavy imports
        import torch
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
        )
        from peft import PeftModel

        # Tokenizer lives in adapter_path/tokenizer/ (Phase 4.3 layout)
        tokenizer_path = os.path.join(artifact_path, "tokenizer")
        if os.path.isdir(tokenizer_path):
            tokenizer = AutoTokenizer.from_pretrained(tokenizer_path)
        else:
            tokenizer = AutoTokenizer.from_pretrained(artifact_path)

        # Load base model with the SAME 4-bit NF4 quantization used in
        # Phase 4.3 training. T4 has no bfloat16, so compute dtype is fp16.
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )
        base = AutoModelForCausalLM.from_pretrained(
            job.base_model,
            quantization_config=bnb_config,
            torch_dtype=torch.float16,
            device_map="auto",
        )
        model = PeftModel.from_pretrained(base, artifact_path)
        model.eval()

        predictions: list[str] = []
        for inp in inputs:
            inputs_enc = tokenizer(inp, return_tensors="pt")
            inputs_enc = {k: v.to(model.device) for k, v in inputs_enc.items()}
            input_len = inputs_enc["input_ids"].shape[-1]
            with torch.no_grad():
                out = model.generate(
                    **inputs_enc,
                    max_new_tokens=128,
                    do_sample=False,
                )
            # Decode only the newly generated tokens, not the input prompt
            pred = tokenizer.decode(
                out[0][input_len:], skip_special_tokens=True
            )
            predictions.append(pred)
        return predictions

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get_evaluation(
        self, evaluation_id: UUID, *, user_id: UUID
    ) -> EvaluationResponse:
        """Return a single evaluation. Raises access denied if not owner."""
        ev = await self._evals.get_by_id(evaluation_id)
        if ev is None:
            raise EvaluationNotFoundError(evaluation_id)
        if ev.user_id != user_id:
            raise EvaluationAccessDeniedError(evaluation_id)
        return EvaluationResponse.model_validate(ev)

    async def list_evaluations(
        self,
        *,
        user_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> EvaluationListResponse:
        """Return paginated evaluations for a user."""
        items = await self._evals.list_for_user(
            user_id, limit=limit, offset=offset
        )
        total = await self._evals.count_for_user(user_id)
        return EvaluationListResponse(
            items=[EvaluationResponse.model_validate(e) for e in items],
            total=total,
            limit=limit,
            offset=offset,
        )
