"""Evaluation metrics: ROUGE-L, BERTScore, semantic similarity.

Heavy ML imports are lazy so the module loads without torch/transformers.
"""

from __future__ import annotations


class MetricError(Exception):
    """Raised when a metric computation fails."""


def _validate_inputs(predictions: list[str], references: list[str]) -> None:
    if not predictions or not references:
        raise MetricError("predictions and references must be non-empty")
    if len(predictions) != len(references):
        raise MetricError(
            f"length mismatch: {len(predictions)} predictions vs "
            f"{len(references)} references"
        )


def compute_rouge_l(predictions: list[str], references: list[str]) -> float:
    _validate_inputs(predictions, references)
    from rouge_score import rouge_scorer

    scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)
    scores = [
        scorer.score(ref, pred)["rougeL"].fmeasure
        for pred, ref in zip(predictions, references)
    ]
    return sum(scores) / len(scores)


def compute_bertscore(
    predictions: list[str], references: list[str]
) -> tuple[float, float, float]:
    _validate_inputs(predictions, references)
    from bert_score import score as bert_score_fn

    P, R, F = bert_score_fn(
        predictions, references, lang="en", verbose=False
    )
    return float(P.mean().item()), float(R.mean().item()), float(F.mean().item())


def compute_semantic_similarity(
    predictions: list[str], references: list[str]
) -> float:
    _validate_inputs(predictions, references)
    from sentence_transformers import SentenceTransformer, util

    model = SentenceTransformer("all-MiniLM-L6-v2")
    pred_emb = model.encode(predictions, convert_to_tensor=True)
    ref_emb = model.encode(references, convert_to_tensor=True)
    cos = util.cos_sim(pred_emb, ref_emb)
    # Rescale [-1,1] → [0,1] along the diagonal (pairwise).
    diag = cos.diagonal()
    return float(((diag + 1.0) / 2.0).mean().item())
