"""Inference service.

Loads a base model + LoRA adapter once and reuses it for generation.
Heavy ML imports are lazy so the module imports cleanly in tests.

ponytail: a plain instance-level cache. The API dependency injects a
module-level singleton so the loaded model survives across requests.
A production backend (vLLM/TGI/Triton) can replace this class without
changing the API contract.
"""

from __future__ import annotations

import os


class InferenceError(Exception):
    """Base exception for inference errors."""

    code = "INFERENCE_ERROR"
    http_status = 400


class InferenceService:
    """Synchronous inference engine backed by transformers + PEFT."""

    def __init__(self) -> None:
        self._key: str | None = None
        self._tokenizer = None
        self._model = None

    @property
    def is_loaded(self) -> bool:
        """True when a model and tokenizer are cached."""
        return self._model is not None

    def _cache_key(self, artifact_path: str, base_model: str) -> str:
        return f"{base_model}:{artifact_path}"

    def load(self, artifact_path: str, base_model: str) -> None:
        """Load tokenizer, base model, and LoRA adapter.

        If the same adapter is already cached, this is a no-op.
        """
        key = self._cache_key(artifact_path, base_model)
        if self._key == key:
            return

        if not os.path.isdir(artifact_path):
            raise InferenceError(
                f"Adapter artifact not found at path: {artifact_path}"
            )

        self.unload()

        # Lazy heavy imports — only pay the cost when we actually infer.
        import torch
        from peft import PeftModel
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
        )

        # Phase 5.1 layout: tokenizer lives in adapter_path/tokenizer/
        tokenizer_path = os.path.join(artifact_path, "tokenizer")
        if os.path.isdir(tokenizer_path):
            tokenizer = AutoTokenizer.from_pretrained(tokenizer_path)
        else:
            tokenizer = AutoTokenizer.from_pretrained(artifact_path)

        # Match the 4-bit NF4 quantization used during Phase 4.3 training.
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )
        base = AutoModelForCausalLM.from_pretrained(
            base_model,
            quantization_config=bnb_config,
            torch_dtype=torch.float16,
            device_map="auto",
        )
        model = PeftModel.from_pretrained(base, artifact_path)
        model.eval()

        self._tokenizer = tokenizer
        self._model = model
        self._key = key

    def generate(
        self,
        prompt: str,
        *,
        max_new_tokens: int = 1024,
        temperature: float = 0.7,
        do_sample: bool = True,
    ) -> str:
        """Generate text for a single prompt using the cached model."""
        if not self.is_loaded:
            raise InferenceError("No model is loaded")

        import torch

        inputs_enc = self._tokenizer(prompt, return_tensors="pt")
        inputs_enc = {
            k: v.to(self._model.device) for k, v in inputs_enc.items()
        }
        input_len = inputs_enc["input_ids"].shape[-1]

        with torch.no_grad():
            out = self._model.generate(
                **inputs_enc,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                do_sample=do_sample,
            )

        # Return only the newly generated tokens.
        return self._tokenizer.decode(
            out[0][input_len:], skip_special_tokens=True
        )

    def unload(self) -> None:
        """Drop the cached model and tokenizer."""
        self._key = None
        self._tokenizer = None
        self._model = None
