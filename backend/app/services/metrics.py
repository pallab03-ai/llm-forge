"""Metric computation functions for the Evaluation Service.

MVP metrics:
- ROUGE-L (rouge-score package)
- BERTScore (bert-score package)
- Semantic Similarity (sentence-transformers package)

All heavy ML imports are LAZY (inside function bodies) so the module
imports cleanly in test environments without torch/transformers installed.
Tests patch these functions at the module level.

Each function takes parallel lists of predictions and references,
returns a float (or tuple for BERTScore). Raises MetricError on failure.
"""

from __future__ import annotations


class MetricError(Exception):
    """Raised when a metric computation fails."""


def compute_rouge_l(predictions: list[str], references: list[str]) -> float:
    """Compute mean ROUGE-L F1 over prediction/reference pairs.

    Returns a float in [0.0, 1.0].
    """
    if not predictions or not references:
        raise MetricError("predictions and references must be non-empty")
    if len(predictions) != len(references):
        raise MetricError(
            f"length mismatch: {len(predictions)} predictions vs "
            f"{len(references)} references"
        )
    # ponytail: lazy import — rouge-score pulls in nltk/absl, avoid at module load
    from rouge_score import rouge_scorer

    scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)
    scores = []
    for pred, ref in zip(predictions, references):
        s = scorer.score(ref, pred)
        scores.append(s["rougeL"].fmeasure)
    return sum(scores) / len(scores)


def compute_bertscore(
    predictions: list[str], references: list[str]
) -> tuple[float, float, float]:
    """Compute mean BERTScore (precision, recall, F1).

    Returns a tuple of three floats in [0.0, 1.0].
    """
    if not predictions or not references:
        raise MetricError("predictions and references must be non-empty")
    if len(predictions) != len(references):
        raise MetricError(
            f"length mismatch: {len(predictions)} predictions vs "
            f"{len(references)} references"
        )
    # ponytail: lazy import — bert-score pulls in torch + transformers
    from bert_score import score as bert_score_fn

    P, R, F = bert_score_fn(
        predictions, references, lang="en", verbose=False
    )
    return float(P.mean().item()), float(R.mean().item()), float(F.mean().item())


def compute_semantic_similarity(
    predictions: list[str], references: list[str]
) -> float:
    """Compute mean cosine semantic similarity using sentence-transformers.

    Returns a float in [0.0, 1.0] (cosine similarity rescaled to [0,1]).
    """
    if not predictions or not references:
        raise MetricError("predictions and references must be non-empty")
    if len(predictions) != len(references):
        raise MetricError(
            f"length mismatch: {len(predictions)} predictions vs "
            f"{len(references)} references"
        )
    # ponytail: lazy import — sentence-transformers pulls in torch + transformers
    from sentence_transformers import SentenceTransformer, util

    model = SentenceTransformer("all-MiniLM-L6-v2")
    pred_emb = model.encode(predictions, convert_to_tensor=True)
    ref_emb = model.encode(references, convert_to_tensor=True)
    cos = util.cos_sim(pred_emb, ref_emb)
    # diagonal = pairwise similarities; rescale [-1,1] → [0,1]
    diag = cos.diagonal()
    return float(((diag + 1.0) / 2.0).mean().item())
