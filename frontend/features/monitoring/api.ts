import { apiClient } from "@/services/api-client";
import type {
  DashboardData,
  ErrorLogList,
  HealthData,
  MetricsData,
  RequestLogList,
} from "./schemas";

export const monitoringApi = {
  getDashboard: () => apiClient.get<DashboardData>("/monitoring/dashboard"),

  getHealth: (deploymentId: string) =>
    apiClient.get<HealthData>(`/deployments/${deploymentId}/health`),

  getMetrics: (deploymentId: string) =>
    apiClient.get<MetricsData>(`/deployments/${deploymentId}/metrics`),

  listRequests: (deploymentId: string, params?: { limit?: number; offset?: number }) =>
    apiClient.get<RequestLogList>(`/deployments/${deploymentId}/requests`, params),

  listErrors: (deploymentId: string, params?: { limit?: number; offset?: number }) =>
    apiClient.get<ErrorLogList>(`/deployments/${deploymentId}/errors`, params),
};
