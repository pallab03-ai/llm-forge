"use client";

import { useQuery } from "@tanstack/react-query";
import { monitoringApi } from "./api";
import {
  DASHBOARD_POLL_MS,
  DEPLOYMENT_POLL_MS,
  type ErrorLogList,
  type HealthData,
  type MetricsData,
  type RequestLogList,
} from "./schemas";

export const monitoringKeys = {
  all: ["monitoring"] as const,
  dashboard: () => [...monitoringKeys.all, "dashboard"] as const,
  health: (id: string) => [...monitoringKeys.all, "health", id] as const,
  metrics: (id: string) => [...monitoringKeys.all, "metrics", id] as const,
  requests: (id: string, limit: number, offset: number) =>
    [...monitoringKeys.all, "requests", id, limit, offset] as const,
  errors: (id: string, limit: number, offset: number) =>
    [...monitoringKeys.all, "errors", id, limit, offset] as const,
};

export function useMonitoringDashboard() {
  return useQuery({
    queryKey: monitoringKeys.dashboard(),
    queryFn: () => monitoringApi.getDashboard(),
    refetchInterval: DASHBOARD_POLL_MS,
    staleTime: 5_000,
  });
}

export function useDeploymentHealth(deploymentId: string) {
  return useQuery<HealthData>({
    queryKey: monitoringKeys.health(deploymentId),
    queryFn: () => monitoringApi.getHealth(deploymentId),
    enabled: Boolean(deploymentId),
    refetchInterval: DEPLOYMENT_POLL_MS,
    staleTime: 5_000,
  });
}

export function useDeploymentMetrics(deploymentId: string) {
  return useQuery<MetricsData>({
    queryKey: monitoringKeys.metrics(deploymentId),
    queryFn: () => monitoringApi.getMetrics(deploymentId),
    enabled: Boolean(deploymentId),
    refetchInterval: DEPLOYMENT_POLL_MS,
    staleTime: 5_000,
  });
}

export function useDeploymentRequests(
  deploymentId: string,
  params: { limit: number; offset: number },
) {
  return useQuery<RequestLogList>({
    queryKey: monitoringKeys.requests(deploymentId, params.limit, params.offset),
    queryFn: () => monitoringApi.listRequests(deploymentId, params),
    enabled: Boolean(deploymentId),
    refetchInterval: DEPLOYMENT_POLL_MS,
    staleTime: 5_000,
  });
}

export function useDeploymentErrors(
  deploymentId: string,
  params: { limit: number; offset: number },
) {
  return useQuery<ErrorLogList>({
    queryKey: monitoringKeys.errors(deploymentId, params.limit, params.offset),
    queryFn: () => monitoringApi.listErrors(deploymentId, params),
    enabled: Boolean(deploymentId),
    refetchInterval: DEPLOYMENT_POLL_MS,
    staleTime: 5_000,
  });
}
