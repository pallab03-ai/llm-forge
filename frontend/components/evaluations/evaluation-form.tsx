"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { useDatasets, useDataset } from "@/features/datasets/queries";
import { useTrainingJobs } from "@/features/training/queries";
import {
  createEvaluationSchema,
  type CreateEvaluationInput,
} from "@/features/evaluations/schemas";
import { useCreateEvaluation } from "@/features/evaluations/queries";
import { ApiError } from "@/services/api-client";

const DEFAULTS: CreateEvaluationInput = {
  model_id: "",
  dataset_id: "",
  dataset_version_id: "",
};

export function EvaluationForm() {
  const router = useRouter();
  const trainingQuery = useTrainingJobs();
  const datasetsQuery = useDatasets();
  const createEvaluation = useCreateEvaluation();

  // ponytail: a model is only eligible if its training job is completed and
  // it has an artifact_path. The backend's ModelNotReadyError enforces this
  // server-side; filtering client-side avoids handing the user a 409.
  const eligibleModels = useMemo(
    () =>
      (trainingQuery.data?.items ?? []).filter(
        (j) => j.status === "completed" && j.artifact_path !== null,
      ),
    [trainingQuery.data],
  );

  const readyDatasets = useMemo(
    () => (datasetsQuery.data?.items ?? []).filter((d) => d.status === "ready"),
    [datasetsQuery.data],
  );

  const form = useForm<CreateEvaluationInput>({
    resolver: zodResolver(createEvaluationSchema),
    defaultValues: DEFAULTS,
  });
  const { register, handleSubmit, setValue, watch, formState: { errors } } = form;

  const [selectedDatasetId, setSelectedDatasetId] = useState<string>("");
  const datasetDetail = useDataset(selectedDatasetId);

  useEffect(() => {
    if (!selectedDatasetId) {
      setValue("dataset_version_id", "", { shouldValidate: false });
      return;
    }
    if (datasetDetail.data) {
      const latest = datasetDetail.data.versions?.[0] ?? null;
      const useable = latest && latest.validation_errors === null ? latest : null;
      setValue("dataset_version_id", useable?.id ?? "", { shouldValidate: false });
    }
  }, [selectedDatasetId, datasetDetail.data, setValue]);

  const [submitError, setSubmitError] = useState<string | null>(null);

  const onSubmit = handleSubmit(async (values) => {
    setSubmitError(null);
    try {
      const evaluation = await createEvaluation.mutateAsync(values);
      toast.success("Evaluation started.");
      router.push(`/evaluations/${evaluation.id}`);
    } catch (error) {
      if (error instanceof ApiError) {
        setSubmitError(error.message);
        return;
      }
      setSubmitError("Network error. Check your connection and try again.");
    }
  });

  const modelId = watch("model_id");

  return (
    <form className="space-y-6" onSubmit={onSubmit} noValidate>
      {submitError ? (
        <div
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
        >
          {submitError}
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Run</CardTitle>
          <CardDescription>Pick a trained model and an evaluation dataset.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="model_id">Trained model</Label>
            <select
              id="model_id"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              {...register("model_id")}
              disabled={trainingQuery.isLoading}
            >
              <option value="">
                {trainingQuery.isLoading
                  ? "Loading training jobs…"
                  : eligibleModels.length === 0
                    ? "No completed models with artifacts"
                    : "Select a model"}
              </option>
              {eligibleModels.map((j) => (
                <option key={j.id} value={j.id}>
                  {j.id.slice(0, 8)} · {j.base_model}
                </option>
              ))}
            </select>
            {errors.model_id ? (
              <p className="text-xs text-destructive">{errors.model_id.message}</p>
            ) : eligibleModels.length === 0 && !trainingQuery.isLoading ? (
              <p className="text-xs text-muted-foreground">
                No completed training jobs with an adapter. Finish a training run first.
              </p>
            ) : null}
            {modelId ? (
              <p className="font-mono text-xs text-muted-foreground">Selected: {modelId.slice(0, 8)}</p>
            ) : null}
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="dataset_id">Evaluation dataset</Label>
              <select
                id="dataset_id"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                value={selectedDatasetId}
                onChange={(e) => {
                  setSelectedDatasetId(e.target.value);
                  setValue("dataset_id", e.target.value, { shouldValidate: true });
                }}
                disabled={datasetsQuery.isLoading}
              >
                <option value="">
                  {datasetsQuery.isLoading
                    ? "Loading datasets…"
                    : readyDatasets.length === 0
                      ? "No ready datasets"
                      : "Select a dataset"}
                </option>
                {readyDatasets.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
              {errors.dataset_id ? (
                <p className="text-xs text-destructive">{errors.dataset_id.message}</p>
              ) : null}
              {readyDatasets.length === 0 && !datasetsQuery.isLoading ? (
                <p className="text-xs text-muted-foreground">
                  No datasets are ready. Upload a dataset first and wait for validation.
                </p>
              ) : null}
            </div>

            <div className="space-y-2">
              <Label>Dataset version</Label>
              <div className="flex h-10 items-center rounded-md border bg-muted/30 px-3 text-sm text-muted-foreground">
                {selectedDatasetId ? (
                  datasetDetail.isLoading ? (
                    <span className="inline-flex items-center gap-2">
                      <Spinner size="sm" /> Loading versions…
                    </span>
                  ) : datasetDetail.data?.versions?.[0] ? (
                    <span>
                      v{datasetDetail.data.versions[0].version_number}
                      {" · "}
                      {datasetDetail.data.versions[0].record_count.toLocaleString()} records
                    </span>
                  ) : (
                    <span>No versions available</span>
                  )
                ) : (
                  <span>Choose a dataset first</span>
                )}
              </div>
              {errors.dataset_version_id ? (
                <p className="text-xs text-destructive">{errors.dataset_version_id.message}</p>
              ) : null}
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button type="submit" disabled={createEvaluation.isPending}>
          {createEvaluation.isPending ? <Spinner size="sm" label="Starting" /> : "Start evaluation"}
        </Button>
      </div>
    </form>
  );
}
