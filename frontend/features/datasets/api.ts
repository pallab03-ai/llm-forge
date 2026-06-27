import { apiClient, uploadFile, type UploadProgressEvent } from "@/services/api-client";
import type { DatasetDetail, DatasetList } from "./schemas";

type UploadOptions = {
  onProgress?: (event: UploadProgressEvent) => void;
  signal?: AbortSignal;
};

export const datasetsApi = {
  list: () => apiClient.get<DatasetList>("/datasets"),

  get: (id: string) => apiClient.get<DatasetDetail>(`/datasets/${id}`),

  upload: (formData: FormData, options: UploadOptions = {}) =>
    uploadFile<DatasetDetail>("/datasets", formData, options),

  uploadVersion: (id: string, formData: FormData, options: UploadOptions = {}) =>
    uploadFile<DatasetDetail>(`/datasets/${id}/versions`, formData, options),
};
