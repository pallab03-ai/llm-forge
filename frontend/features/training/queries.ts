"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { trainingApi } from "./api";
import {
  ACTIVE_POLL_MS,
  isActiveStatus,
  type CreateTrainingJobInput,
  type TrainingJob,
} from "./schemas";

export const trainingKeys = {
  all: ["training-jobs"] as const,
  list: () => [...trainingKeys.all, "list"] as const,
  detail: (id: string) => [...trainingKeys.all, "detail", id] as const,
};

export function useTrainingJobs() {
  return useQuery({
    queryKey: trainingKeys.list(),
    queryFn: () => trainingApi.list({ limit: 100, offset: 0 }),
    staleTime: 30_000,
  });
}

// ponytail: live status polling only when the job is still in an active
// state. The refetchInterval callback returns a number while active and
// false once the job is terminal, so TanStack stops polling automatically.
export function useTrainingJob(id: string) {
  return useQuery({
    queryKey: trainingKeys.detail(id),
    queryFn: () => trainingApi.get(id),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && isActiveStatus(status) ? ACTIVE_POLL_MS : false;
    },
    staleTime: 5_000,
  });
}

export function useCreateTrainingJob() {
  const qc = useQueryClient();
  return useMutation<TrainingJob, Error, CreateTrainingJobInput>({
    mutationFn: (input) => trainingApi.create(input),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: trainingKeys.list() });
      qc.setQueryData(trainingKeys.detail(data.id), data);
    },
  });
}

export function useCancelTrainingJob() {
  const qc = useQueryClient();
  return useMutation<TrainingJob, Error, string>({
    mutationFn: (id) => trainingApi.cancel(id),
    onSuccess: (data) => {
      qc.setQueryData(trainingKeys.detail(data.id), data);
      qc.invalidateQueries({ queryKey: trainingKeys.list() });
    },
  });
}
