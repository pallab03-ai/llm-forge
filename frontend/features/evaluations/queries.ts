"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { evaluationApi } from "./api";
import {
  ACTIVE_POLL_MS,
  isActiveEvaluationStatus,
  type CreateEvaluationInput,
  type Evaluation,
} from "./schemas";

export const evaluationKeys = {
  all: ["evaluations"] as const,
  list: () => [...evaluationKeys.all, "list"] as const,
  detail: (id: string) => [...evaluationKeys.all, "detail", id] as const,
};

export function useEvaluations() {
  return useQuery({
    queryKey: evaluationKeys.list(),
    queryFn: () => evaluationApi.list({ limit: 100, offset: 0 }),
    staleTime: 30_000,
  });
}

// ponytail: live status polling only while the evaluation is active. The
// refetchInterval callback returns a number while pending/running and false
// once the row reaches a terminal state, so TanStack stops polling.
export function useEvaluation(id: string) {
  return useQuery({
    queryKey: evaluationKeys.detail(id),
    queryFn: () => evaluationApi.get(id),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && isActiveEvaluationStatus(status) ? ACTIVE_POLL_MS : false;
    },
    staleTime: 5_000,
  });
}

export function useCreateEvaluation() {
  const qc = useQueryClient();
  return useMutation<Evaluation, Error, CreateEvaluationInput>({
    mutationFn: (input) => evaluationApi.create(input),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: evaluationKeys.list() });
      qc.setQueryData(evaluationKeys.detail(data.id), data);
    },
  });
}
