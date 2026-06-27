import { apiClient } from "@/services/api-client";
import type {
  CreateDeploymentInput,
  Deployment,
  DeploymentList,
  GenerateResponse_,
} from "./schemas";

export const deploymentApi = {
  list: (params?: { limit?: number; offset?: number }) =>
    apiClient.get<DeploymentList>("/deployments", params),

  get: (id: string) => apiClient.get<Deployment>(`/deployments/${id}`),

  create: (input: CreateDeploymentInput) =>
    apiClient.post<Deployment>("/deployments", {
      model_version_id: input.model_version_id,
      deployment_name: input.deployment_name,
      endpoint_name: input.endpoint_name,
    }),

  activate: (id: string) =>
    apiClient.post<Deployment>(`/deployments/${id}/activate`),

  generate: (id: string, prompt: string) =>
    apiClient.post<GenerateResponse_>(`/deployments/${id}/generate`, { prompt }),
};
