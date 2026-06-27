import { z } from "zod";

// ponytail: backend ModelVersionStatus has 4 values: draft, staging,
// production, archived. Mirrored exactly.
export const modelVersionStatusValues = ["draft", "staging", "production", "archived"] as const;
export type ModelVersionStatus = (typeof modelVersionStatusValues)[number];

export const REGISTRY_STATUS_LABELS: Record<ModelVersionStatus, string> = {
  draft: "Draft",
  staging: "Staging",
  production: "Production",
  archived: "Archived",
};

export const REGISTRY_STATUS_VARIANTS: Record<
  ModelVersionStatus,
  "secondary" | "info" | "success" | "warning"
> = {
  draft: "secondary",
  staging: "info",
  production: "success",
  archived: "warning",
};

export const createModelSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Name is required.")
    .max(255, "Name must be 255 characters or fewer."),
  description: z
    .string()
    .max(1000, "Description must be 1000 characters or fewer.")
    .optional()
    .or(z.literal("")),
  training_job_id: z.string().min(1, "Choose a training job."),
  evaluation_id: z.string().min(1, "Choose an evaluation."),
});

export type CreateModelInput = z.infer<typeof createModelSchema>;

export type ModelVersion = {
  id: string;
  model_id: string;
  training_job_id: string;
  evaluation_id: string;
  version_number: number;
  artifact_path: string;
  metrics_snapshot: Record<string, number | null> | null;
  status: ModelVersionStatus;
  created_at: string;
  updated_at: string;
};

export type Model = {
  id: string;
  owner_id: string;
  name: string;
  description: string | null;
  versions: ModelVersion[];
  created_at: string;
  updated_at: string;
};

export type ModelList = {
  items: Model[];
  total: number;
  limit: number;
  offset: number;
};

export function headVersion(model: Model): ModelVersion | null {
  return model.versions.length > 0 ? model.versions[0] : null;
}
