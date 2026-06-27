import { apiClient } from "@/services/api-client";
import type { CreateModelInput, Model, ModelList, ModelVersion } from "./schemas";

export const modelApi = {
  list: (params?: { limit?: number; offset?: number }) =>
    apiClient.get<ModelList>("/models", params),

  get: (id: string) => apiClient.get<Model>(`/models/${id}`),

  create: (input: Pick<CreateModelInput, "name" | "description">) =>
    apiClient.post<Model>("/models", {
      name: input.name,
      description: input.description || null,
    }),

  createVersion: (modelId: string, input: { training_job_id: string; evaluation_id: string }) =>
    apiClient.post<ModelVersion>(`/models/${modelId}/versions`, {
      training_job_id: input.training_job_id,
      evaluation_id: input.evaluation_id,
    }),

  promoteVersion: (versionId: string) =>
    apiClient.post<ModelVersion>(`/models/versions/${versionId}/promote`),

  archiveVersion: (versionId: string) =>
    apiClient.post<ModelVersion>(`/models/versions/${versionId}/archive`),
};
