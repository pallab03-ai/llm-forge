import { z } from "zod";

// ponytail: backend EvaluationStatus has 4 values: pending, running,
// completed, failed. No `cancelled`. Mirrored exactly — no invented states.
export const evaluationStatusValues = ["pending", "running", "completed", "failed"] as const;
export type EvaluationStatus = (typeof evaluationStatusValues)[number];

export const EVALUATION_STATUS_LABELS: Record<EvaluationStatus, string> = {
  pending: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
};

export const EVALUATION_STATUS_VARIANTS: Record<
  EvaluationStatus,
  "secondary" | "info" | "success" | "danger"
> = {
  pending: "secondary",
  running: "info",
  completed: "success",
  failed: "danger",
};

export const ACTIVE_POLL_MS = 2000;

export function isActiveEvaluationStatus(status: EvaluationStatus): boolean {
  return status === "pending" || status === "running";
}

// ponytail: backend EvaluationCreateRequest has exactly three UUID fields
// (model_id, dataset_id, dataset_version_id) with extra="forbid". The spec
// mentioned an "Evaluation Type" field but the backend does not expose one;
// the form only collects the three UUIDs the API accepts.
export const createEvaluationSchema = z.object({
  model_id: z.string().min(1, "Choose a trained model."),
  dataset_id: z.string().min(1, "Choose a dataset."),
  dataset_version_id: z.string().min(1, "Choose a dataset version."),
});

export type CreateEvaluationInput = z.infer<typeof createEvaluationSchema>;

export type Evaluation = {
  id: string;
  user_id: string;
  dataset_id: string;
  dataset_version_id: string;
  model_id: string;
  status: EvaluationStatus;
  rouge_score: number | null;
  bertscore_precision: number | null;
  bertscore_recall: number | null;
  bertscore_f1: number | null;
  semantic_similarity: number | null;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type EvaluationList = {
  items: Evaluation[];
  total: number;
  limit: number;
  offset: number;
};

// ponytail: backend returns exactly these five metric fields. Spec listed
// accuracy/precision/recall/F1 as examples; the backend does not compute
// per-prediction classification metrics. Only the five fields below are
// surfaced as cards; the rest are not invented.
export const METRIC_FIELDS = [
  "rouge_score",
  "bertscore_precision",
  "bertscore_recall",
  "bertscore_f1",
  "semantic_similarity",
] as const;
export type MetricField = (typeof METRIC_FIELDS)[number];

export const METRICS: ReadonlyArray<{
  field: MetricField;
  label: string;
  description: string;
}> = [
  {
    field: "rouge_score",
    label: "ROUGE-L",
    description: "Longest common subsequence F1 against reference responses.",
  },
  {
    field: "bertscore_precision",
    label: "BERTScore Precision",
    description: "Contextual precision of generated tokens (0–1).",
  },
  {
    field: "bertscore_recall",
    label: "BERTScore Recall",
    description: "Contextual recall of generated tokens (0–1).",
  },
  {
    field: "bertscore_f1",
    label: "BERTScore F1",
    description: "F1 of BERTScore precision and recall (0–1).",
  },
  {
    field: "semantic_similarity",
    label: "Semantic Similarity",
    description: "Mean cosine similarity of sentence embeddings (0–1).",
  },
];

export function formatMetricValue(value: number | null): string {
  if (value === null || value === undefined) return "—";
  return value.toFixed(4);
}
