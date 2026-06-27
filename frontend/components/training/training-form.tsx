"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useMemo, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { useDataset } from "@/features/datasets/queries";
import {
  SUPPORTED_BASE_MODELS,
  TRAINING_TYPE_DESCRIPTIONS,
  TRAINING_TYPE_LABELS,
  createTrainingJobSchema,
  trainingTypeValues,
  type CreateTrainingJobInput,
} from "@/features/training/schemas";
import { useCreateTrainingJob } from "@/features/training/queries";
import { useDatasets } from "@/features/datasets/queries";
import { useRouter } from "next/navigation";
import { ApiError } from "@/services/api-client";

const DEFAULTS: Omit<CreateTrainingJobInput, "configuration"> & {
  configuration: CreateTrainingJobInput["configuration"];
} = {
  name: "",
  base_model: "",
  dataset_id: "",
  dataset_version_id: "",
  training_type: "lora",
  configuration: {
    epochs: 3,
    batch_size: 4,
    learning_rate: 0.0002,
    max_seq_length: 512,
  },
};

export function TrainingForm() {
  const router = useRouter();
  const datasetsQuery = useDatasets();
  const readyDatasets = useMemo(
    () => (datasetsQuery.data?.items ?? []).filter((d) => d.status === "ready"),
    [datasetsQuery.data],
  );
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>("");
  const datasetDetail = useDataset(selectedDatasetId);
  const createJob = useCreateTrainingJob();
  const [submitError, setSubmitError] = useState<string | null>(null);

  const form = useForm<CreateTrainingJobInput>({
    resolver: zodResolver(createTrainingJobSchema),
    defaultValues: DEFAULTS,
  });
  const {
    register,
    handleSubmit,
    setValue,
    control,
    formState: { errors },
  } = form;

  // ponytail: when the user picks a dataset, the form must wait for the
  // detail fetch (which carries versions) and pre-fill dataset_version_id
  // with the latest ready version. We do not auto-submit; the user still
  // presses the button.
  useEffect(() => {
    if (!selectedDatasetId) {
      setValue("dataset_version_id", "", { shouldValidate: false });
      return;
    }
    if (datasetDetail.data) {
      const latest = datasetDetail.data.versions?.[0] ?? null;
      // ponytail: only ready/clean versions are usable. The backend has no
      // "valid" boolean on the version, so we use validation_errors === null
      // as the success signal (matches the dataset detail page logic).
      const useable = latest && latest.validation_errors === null ? latest : null;
      setValue("dataset_version_id", useable?.id ?? "", { shouldValidate: false });
    }
  }, [selectedDatasetId, datasetDetail.data, setValue]);

  const onSubmit = handleSubmit(async (values) => {
    setSubmitError(null);
    try {
      const job = await createJob.mutateAsync(values);
      toast.success("Training job created.");
      router.push(`/training/${job.id}`);
    } catch (error) {
      if (error instanceof ApiError) {
        setSubmitError(error.message);
        return;
      }
      setSubmitError("Network error. Check your connection and try again.");
    }
  });

  return (
    <form className="space-y-6" onSubmit={onSubmit} noValidate>
      {submitError ? (
        <div role="alert" className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          {submitError}
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Job</CardTitle>
          <CardDescription>Identify the run and pick inputs.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Job name</Label>
            <Input
              id="name"
              placeholder="instruction-tune-1"
              invalid={Boolean(errors.name)}
              {...register("name")}
            />
            {errors.name ? <p className="text-xs text-destructive">{errors.name.message}</p> : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="base_model">Base model</Label>
            <Input
              id="base_model"
              placeholder="meta-llama/Meta-Llama-3.1-8B-Instruct"
              list="supported-base-models"
              invalid={Boolean(errors.base_model)}
              {...register("base_model")}
            />
            <datalist id="supported-base-models">
              {SUPPORTED_BASE_MODELS.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
            {errors.base_model ? (
              <p className="text-xs text-destructive">{errors.base_model.message}</p>
            ) : (
              <p className="text-xs text-muted-foreground">
                Use a HuggingFace model id. Pick from the list or type your own.
              </p>
            )}
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="dataset_id">Dataset</Label>
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
                  No datasets are ready. Upload a dataset first and wait for validation to complete.
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

          <div className="space-y-2">
            <Label htmlFor="training_type">Training method</Label>
            <Controller
              control={control}
              name="training_type"
              render={({ field }) => (
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {trainingTypeValues.map((value) => (
                    <label
                      key={value}
                      className={`flex cursor-pointer flex-col gap-1 rounded-md border p-3 text-sm transition-colors ${
                        field.value === value
                          ? "border-primary bg-primary/5"
                          : "border-input hover:bg-accent/30"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-medium">{TRAINING_TYPE_LABELS[value]}</span>
                        <input
                          type="radio"
                          name={field.name}
                          value={value}
                          checked={field.value === value}
                          onChange={() => field.onChange(value)}
                          onBlur={field.onBlur}
                        />
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {TRAINING_TYPE_DESCRIPTIONS[value]}
                      </span>
                    </label>
                  ))}
                </div>
              )}
            />
            {errors.training_type ? (
              <p className="text-xs text-destructive">{errors.training_type.message}</p>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Training parameters</CardTitle>
          <CardDescription>
            The four fields the backend accepts. Other knobs (LoRA rank, gradient accumulation,
            seed) are not yet exposed by the API and are intentionally omitted.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="epochs">Epochs</Label>
            <Input
              id="epochs"
              type="number"
              min={1}
              max={10}
              step={1}
              invalid={Boolean(errors.configuration?.epochs)}
              {...register("configuration.epochs")}
            />
            {errors.configuration?.epochs ? (
              <p className="text-xs text-destructive">{errors.configuration.epochs.message}</p>
            ) : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="batch_size">Batch size</Label>
            <Input
              id="batch_size"
              type="number"
              min={1}
              max={64}
              step={1}
              invalid={Boolean(errors.configuration?.batch_size)}
              {...register("configuration.batch_size")}
            />
            {errors.configuration?.batch_size ? (
              <p className="text-xs text-destructive">{errors.configuration.batch_size.message}</p>
            ) : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="learning_rate">Learning rate</Label>
            <Input
              id="learning_rate"
              type="number"
              step="0.00001"
              invalid={Boolean(errors.configuration?.learning_rate)}
              {...register("configuration.learning_rate")}
            />
            {errors.configuration?.learning_rate ? (
              <p className="text-xs text-destructive">{errors.configuration.learning_rate.message}</p>
            ) : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="max_seq_length">Max sequence length</Label>
            <Input
              id="max_seq_length"
              type="number"
              min={64}
              max={8192}
              step={1}
              invalid={Boolean(errors.configuration?.max_seq_length)}
              {...register("configuration.max_seq_length")}
            />
            {errors.configuration?.max_seq_length ? (
              <p className="text-xs text-destructive">{errors.configuration.max_seq_length.message}</p>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button type="submit" disabled={createJob.isPending}>
          {createJob.isPending ? <Spinner size="sm" label="Creating" /> : "Create training job"}
        </Button>
      </div>
    </form>
  );
}
