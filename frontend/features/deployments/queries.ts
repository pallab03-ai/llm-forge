"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { deploymentApi } from "./api";
import type { CreateDeploymentInput, Deployment, GenerateResponse_ } from "./schemas";

export const deploymentKeys = {
  all: ["deployments"] as const,
  list: () => [...deploymentKeys.all, "list"] as const,
  detail: (id: string) => [...deploymentKeys.all, "detail", id] as const,
};

export function useDeployments() {
  return useQuery({
    queryKey: deploymentKeys.list(),
    queryFn: () => deploymentApi.list({ limit: 100, offset: 0 }),
    staleTime: 30_000,
  });
}

export function useDeployment(id: string) {
  return useQuery({
    queryKey: deploymentKeys.detail(id),
    queryFn: () => deploymentApi.get(id),
    enabled: Boolean(id),
    staleTime: 5_000,
  });
}

export function useCreateDeployment() {
  const qc = useQueryClient();
  return useMutation<Deployment, Error, CreateDeploymentInput>({
    mutationFn: (input) => deploymentApi.create(input),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: deploymentKeys.list() });
      qc.setQueryData(deploymentKeys.detail(data.id), data);
    },
  });
}

export function useActivateDeployment() {
  const qc = useQueryClient();
  return useMutation<Deployment, Error, string>({
    mutationFn: (id) => deploymentApi.activate(id),
    onSuccess: (data) => {
      qc.setQueryData(deploymentKeys.detail(data.id), data);
      qc.invalidateQueries({ queryKey: deploymentKeys.list() });
    },
  });
}

export function useGenerate(deploymentId: string) {
  return useMutation<GenerateResponse_, Error, string>({
    mutationFn: (prompt) => deploymentApi.generate(deploymentId, prompt),
  });
}
