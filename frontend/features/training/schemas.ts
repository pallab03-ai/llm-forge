import { z } from "zod";

export const trainingTypeValues = ["sft", "lora", "qlora", "peft"] as const;
export type TrainingType = (typeof trainingTypeValues)[number];

export const trainingStatusValues = [
  "queued",
  "running",
  "completed",
  "failed",
  "cancelled",
] as const;
export type TrainingStatus = (typeof trainingStatusValues)[number];

// ponytail: the backend's TrainingConfig uses extra="forbid". The spec lists
// LoRA rank/alpha/dropout, gradient accumulation, gradient checkpointing,
// and seed, but the schema has only epochs/batch_size/learning_rate/
// max_seq_length. Honoring "Do NOT invent backend functionality", the form
// only collects the four fields the backend accepts. The OOM guard
// batch_size * max_seq_length <= 262144 is enforced server-side.
export const trainingConfigSchema = z
  .object({
    epochs: z.coerce
      .number({ invalid_type_error: "Epochs must be a number." })
      .int("Epochs must be a whole number.")
      .min(1, "Epochs must be at least 1.")
      .max(10, "Epochs must be at most 10."),
    batch_size: z.coerce
      .number({ invalid_type_error: "Batch size must be a number." })
      .int("Batch size must be a whole number.")
      .min(1, "Batch size must be at least 1.")
      .max(64, "Batch size must be at most 64."),
    learning_rate: z.coerce
      .number({ invalid_type_error: "Learning rate must be a number." })
      .min(1e-7, "Learning rate is too small.")
      .max(1, "Learning rate is too large."),
    max_seq_length: z.coerce
      .number({ invalid_type_error: "Max sequence length must be a number." })
      .int("Max sequence length must be a whole number.")
      .min(64, "Max sequence length must be at least 64.")
      .max(8192, "Max sequence length must be at most 8192."),
  })
  .refine(
    (value) => value.batch_size * value.max_seq_length <= 262144,
    {
      message: "batch_size * max_seq_length must be at most 262144 for a 16 GB GPU.",
      path: ["max_seq_length"],
    },
  );

export const createTrainingJobSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Job name is required.")
    .max(255, "Job name must be 255 characters or fewer."),
  base_model: z
    .string()
    .trim()
    .min(1, "Base model is required.")
    .max(255, "Base model must be 255 characters or fewer."),
  dataset_id: z.string().min(1, "Choose a dataset."),
  dataset_version_id: z.string().min(1, "Choose a dataset version."),
  training_type: z.enum(trainingTypeValues, {
    errorMap: () => ({ message: "Choose a training method." }),
  }),
  configuration: trainingConfigSchema,
});

export type CreateTrainingJobInput = z.infer<typeof createTrainingJobSchema>;
export type TrainingConfigInput = z.infer<typeof trainingConfigSchema>;

export const TRAINING_TYPE_LABELS: Record<TrainingType, string> = {
  sft: "SFT (Supervised Fine-Tuning)",
  lora: "LoRA",
  qlora: "QLoRA",
  peft: "PEFT",
};

export const TRAINING_TYPE_DESCRIPTIONS: Record<TrainingType, string> = {
  sft: "Full-parameter supervised fine-tuning. Best quality, highest memory cost.",
  lora: "Low-Rank Adaptation. Trains small adapter matrices; the underlying weights stay frozen.",
  qlora: "4-bit quantized base + LoRA adapters. Lowest memory cost.",
  peft: "Parameter-Efficient Fine-Tuning (HuggingFace PEFT library).",
};

export const TRAINING_STATUS_LABELS: Record<TrainingStatus, string> = {
  queued: "Queued",
  running: "Training",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

export const TRAINING_STATUS_VARIANTS: Record<
  TrainingStatus,
  "secondary" | "info" | "success" | "danger" | "default"
> = {
  queued: "secondary",
  running: "info",
  completed: "success",
  failed: "danger",
  cancelled: "default",
};

// ponytail: base-model list. The backend does not expose a model registry
// endpoint, so the datalist is a hint rather than a closed set. Users can
// type any HuggingFace model id.
export const SUPPORTED_BASE_MODELS = [
  "google/gemma-3-1b-it",
  "google/gemma-3-4b-it",
  "meta-llama/Meta-Llama-3-8B-Instruct",
  "meta-llama/Meta-Llama-3.1-8B-Instruct",
  "mistralai/Mistral-7B-Instruct-v0.3",
  "Qwen/Qwen2.5-7B-Instruct",
  "microsoft/Phi-3-mini-4k-instruct",
  "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
];

export const ACTIVE_POLL_MS = 2000;

export function isActiveStatus(status: TrainingStatus): boolean {
  return status === "queued" || status === "running";
}

export type TrainingJob = {
  id: string;
  user_id: string;
  dataset_id: string;
  dataset_version_id: string;
  status: TrainingStatus;
  base_model: string;
  training_type: TrainingType;
  configuration: Record<string, unknown>;
  artifact_path: string | null;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type TrainingJobList = {
  items: TrainingJob[];
  total: number;
  limit: number;
  offset: number;
};
