"use client";

import { useQuery } from "@tanstack/react-query";
import { dashboardApi } from "@/features/dashboard/api";
import { useAuth } from "@/hooks/use-auth";

const STALE_TIME = 30_000;

export function useDashboardData() {
  const { user } = useAuth();

  const datasets = useQuery({
    queryKey: ["dashboard", "count", "datasets"] as const,
    queryFn: dashboardApi.datasets,
    staleTime: STALE_TIME,
  });

  const trainingJobs = useQuery({
    queryKey: ["dashboard", "count", "training-jobs"] as const,
    queryFn: dashboardApi.trainingJobs,
    staleTime: STALE_TIME,
  });

  const evaluations = useQuery({
    queryKey: ["dashboard", "count", "evaluations"] as const,
    queryFn: dashboardApi.evaluations,
    staleTime: STALE_TIME,
  });

  const models = useQuery({
    queryKey: ["dashboard", "count", "models"] as const,
    queryFn: dashboardApi.models,
    staleTime: STALE_TIME,
  });

  const deployments = useQuery({
    queryKey: ["dashboard", "count", "deployments"] as const,
    queryFn: dashboardApi.deployments,
    staleTime: STALE_TIME,
  });

  const health = useQuery({
    queryKey: ["dashboard", "health"] as const,
    queryFn: dashboardApi.health,
    staleTime: STALE_TIME,
  });

  return { user, datasets, trainingJobs, evaluations, models, deployments, health };
}
