import { apiClient } from "@/services/api-client";
import type { CreateEvaluationInput, Evaluation, EvaluationList } from "./schemas";

export const evaluationApi = {
  list: (params?: { limit?: number; offset?: number }) =>
    apiClient.get<EvaluationList>("/evaluations", params),

  get: (id: string) => apiClient.get<Evaluation>(`/evaluations/${id}`),

  create: (input: CreateEvaluationInput) =>
    apiClient.post<Evaluation>("/evaluations", {
      model_id: input.model_id,
      dataset_id: input.dataset_id,
      dataset_version_id: input.dataset_version_id,
    }),
};
