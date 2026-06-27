"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { datasetsApi } from "./api";
import type { DatasetDetail } from "./schemas";

export const datasetKeys = {
  all: ["datasets"] as const,
  list: () => [...datasetKeys.all, "list"] as const,
  detail: (id: string) => [...datasetKeys.all, "detail", id] as const,
};

export function useDatasets() {
  return useQuery({
    queryKey: datasetKeys.list(),
    queryFn: datasetsApi.list,
    staleTime: 30_000,
  });
}

export function useDataset(id: string) {
  return useQuery({
    queryKey: datasetKeys.detail(id),
    queryFn: () => datasetsApi.get(id),
    enabled: Boolean(id),
    staleTime: 30_000,
  });
}

export function useUploadDataset() {
  const qc = useQueryClient();
  return useMutation<DatasetDetail, Error, { formData: FormData; signal?: AbortSignal }>({
    mutationFn: ({ formData, signal }) => datasetsApi.upload(formData, { signal }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: datasetKeys.list() });
      qc.setQueryData(datasetKeys.detail(data.id), data);
    },
  });
}
