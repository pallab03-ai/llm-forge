import { apiClient } from "@/services/api-client";
import type {
  CreateTrainingJobInput,
  TrainingJob,
  TrainingJobList,
} from "./schemas";

export const trainingApi = {
  list: (params?: { limit?: number; offset?: number }) =>
    apiClient.get<TrainingJobList>("/training-jobs", params),

  get: (id: string) => apiClient.get<TrainingJob>(`/training-jobs/${id}`),

  create: (input: CreateTrainingJobInput) =>
    apiClient.post<TrainingJob>("/training-jobs", {
      dataset_id: input.dataset_id,
      dataset_version_id: input.dataset_version_id,
      base_model: input.base_model,
      training_type: input.training_type,
      configuration: input.configuration,
    }),

  cancel: (id: string) =>
    apiClient.post<TrainingJob>(`/training-jobs/${id}/cancel`),
};
