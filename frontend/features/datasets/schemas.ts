import { z } from "zod";

export const datasetTypeValues = ["instruction_tuning", "chat", "qa"] as const;
export const datasetFormatValues = ["csv", "json", "jsonl"] as const;

export type DatasetType = (typeof datasetTypeValues)[number];
export type DatasetFormat = (typeof datasetFormatValues)[number];
export type DatasetStatus = "uploading" | "validating" | "ready" | "failed" | "deleted";

export const DATASET_LABELS: Record<DatasetType, string> = {
  instruction_tuning: "Instruction tuning",
  chat: "Chat",
  qa: "Question answering",
};

export const FORMAT_LABELS: Record<DatasetFormat, string> = {
  csv: "CSV",
  json: "JSON",
  jsonl: "JSON Lines",
};

export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;
export const DATASET_MAX_UPLOAD_HINT = "50 MB";

export type DatasetItem = {
  id: string;
  name: string;
  description: string | null;
  dataset_type: DatasetType;
  format: DatasetFormat;
  status: DatasetStatus;
  created_by: string | null;
  created_at: string;
  updated_at: string;
};

export type DatasetVersion = {
  id: string;
  dataset_id: string;
  version_number: number;
  file_size_bytes: number;
  record_count: number;
  duplicate_count: number;
  validation_errors: string | null;
  statistics: string | null;
  created_at: string;
  updated_at: string;
};

export type DatasetDetail = DatasetItem & {
  versions: DatasetVersion[];
};

export type DatasetList = {
  items: DatasetItem[];
  total: number;
  limit: number;
  offset: number;
};

export type ValidationEntry = {
  code: string;
  severity: "pass" | "warning" | "fail";
  message: string;
};

export const uploadDatasetSchema = z.object({
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
  datasetType: z.enum(datasetTypeValues, {
    errorMap: () => ({ message: "Choose a dataset type." }),
  }),
  format: z.enum(datasetFormatValues, {
    errorMap: () => ({ message: "Choose a file format." }),
  }),
});

export type UploadDatasetInput = z.infer<typeof uploadDatasetSchema>;
