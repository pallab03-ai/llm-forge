"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { modelApi } from "./api";
import type { Model, ModelVersion } from "./schemas";

export const modelKeys = {
  all: ["models"] as const,
  list: () => [...modelKeys.all, "list"] as const,
  detail: (id: string) => [...modelKeys.all, "detail", id] as const,
};

export function useModels() {
  return useQuery({
    queryKey: modelKeys.list(),
    queryFn: () => modelApi.list({ limit: 100, offset: 0 }),
    staleTime: 30_000,
  });
}

export function useModel(id: string) {
  return useQuery({
    queryKey: modelKeys.detail(id),
    queryFn: () => modelApi.get(id),
    enabled: Boolean(id),
    staleTime: 5_000,
  });
}

export function useCreateModel() {
  const qc = useQueryClient();
  return useMutation<Model, Error, { name: string; description?: string }>({
    mutationFn: (input) => modelApi.create(input),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: modelKeys.list() });
      qc.setQueryData(modelKeys.detail(data.id), data);
    },
  });
}

export function useCreateModelVersion() {
  const qc = useQueryClient();
  return useMutation<
    ModelVersion,
    Error,
    { modelId: string; training_job_id: string; evaluation_id: string }
  >({
    // ponytail: pass modelId inside the mutation variables. The model
    // container is created just before this mutation runs, so the modelId
    // is not known at hook-instantiation time. Capturing it via the
    // variables keeps the closure fresh.
    mutationFn: (input) =>
      modelApi.createVersion(input.modelId, {
        training_job_id: input.training_job_id,
        evaluation_id: input.evaluation_id,
      }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: modelKeys.detail(data.model_id) });
      qc.invalidateQueries({ queryKey: modelKeys.list() });
    },
  });
}

export function usePromoteVersion(modelId: string) {
  const qc = useQueryClient();
  return useMutation<ModelVersion, Error, string>({
    mutationFn: (versionId) => modelApi.promoteVersion(versionId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: modelKeys.detail(modelId) });
      qc.invalidateQueries({ queryKey: modelKeys.list() });
    },
  });
}

export function useArchiveVersion(modelId: string) {
  const qc = useQueryClient();
  return useMutation<ModelVersion, Error, string>({
    mutationFn: (versionId) => modelApi.archiveVersion(versionId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: modelKeys.detail(modelId) });
      qc.invalidateQueries({ queryKey: modelKeys.list() });
    },
  });
}
