import { apiClient } from "@/services/api-client";

type ListResponse = {
  items: unknown[];
  total: number;
  limit: number;
  offset: number;
};

export type HealthData = {
  status: string;
  version?: string;
  environment?: string;
};

// ponytail: list endpoints return { items, total, ... }. limit=1 is the smallest
// valid value (ge=1 on the backend) and gives us `total` without a full payload.
async function countOf(path: string): Promise<number> {
  const res = await apiClient.get<ListResponse>(path, { limit: 1, offset: 0 });
  return res.total;
}

export const dashboardApi = {
  datasets: () => countOf("/datasets"),
  trainingJobs: () => countOf("/training-jobs"),
  evaluations: () => countOf("/evaluations"),
  models: () => countOf("/models"),
  deployments: () => countOf("/deployments"),
  health: () => apiClient.get<HealthData>("/health"),
};
