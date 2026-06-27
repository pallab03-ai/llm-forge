"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { useEvaluations } from "@/features/evaluations/queries";
import { useTrainingJobs } from "@/features/training/queries";
import {
  createModelSchema,
  type CreateModelInput,
} from "@/features/models/schemas";
import { useCreateModel, useCreateModelVersion } from "@/features/models/queries";
import { ApiError } from "@/services/api-client";

const DEFAULTS: CreateModelInput = {
  name: "",
  description: "",
  training_job_id: "",
  evaluation_id: "",
};

export function ModelForm() {
  const router = useRouter();
  const trainingQuery = useTrainingJobs();
  const evaluationsQuery = useEvaluations();
  const createModel = useCreateModel();

  // ponytail: a training job is only eligible if it is completed and has
  // an artifact_path. The backend's TrainingJobNotReadyError (409) enforces
  // the same rule; the client filter avoids handing the user a 409.
  const eligibleJobs = useMemo(
    () =>
      (trainingQuery.data?.items ?? []).filter(
        (j) => j.status === "completed" && j.artifact_path !== null,
      ),
    [trainingQuery.data],
  );

  // ponytail: evaluations are only eligible if they completed AND reference
  // the selected training job. The pairing check is enforced server-side; we
  // filter on completion status and let the backend reject cross-linked
  // pairs with a 409 that the form surfaces inline.
  const eligibleEvaluations = useMemo(
    () => (evaluationsQuery.data?.items ?? []).filter((e) => e.status === "completed"),
    [evaluationsQuery.data],
  );

  const form = useForm<CreateModelInput>({
    resolver: zodResolver(createModelSchema),
    defaultValues: DEFAULTS,
  });
  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = form;

  const [selectedTrainingJobId, setSelectedTrainingJobId] = useState<string>("");
  const createVersion = useCreateModelVersion();

  useEffect(() => {
    if (!selectedTrainingJobId) {
      setValue("evaluation_id", "", { shouldValidate: false });
    }
  }, [selectedTrainingJobId, setValue]);

  const trainingJobId = watch("training_job_id");
  const evaluationId = watch("evaluation_id");

  const [submitError, setSubmitError] = useState<string | null>(null);

  const onSubmit = handleSubmit(async (values) => {
    setSubmitError(null);
    try {
      const model = await createModel.mutateAsync({
        name: values.name,
        description: values.description || undefined,
      });
      // ponytail: chain the version create. If the first call succeeded but
      // this one fails, the user has an orphan model and a clear error
      // message; the detail page exposes promote/archive for whatever got
      // registered, and a re-submit can register the first version.
      try {
        await createVersion.mutateAsync({
          modelId: model.id,
          training_job_id: values.training_job_id,
          evaluation_id: values.evaluation_id,
        });
      } catch (error) {
        if (error instanceof ApiError) {
          setSubmitError(
            `Model "${values.name}" was created, but the version registration failed: ${error.message}`,
          );
          return;
        }
        setSubmitError(
          `Model "${values.name}" was created, but the version registration failed due to a network error.`,
        );
        return;
      }
      toast.success("Model registered.");
      router.push(`/models/${model.id}`);
    } catch (error) {
      if (error instanceof ApiError) {
        setSubmitError(error.message);
        return;
      }
      setSubmitError("Network error. Check your connection and try again.");
    }
  });

  const isPending = createModel.isPending || createVersion.isPending;

  return (
    <form className="space-y-6" onSubmit={onSubmit} noValidate>
      {submitError ? (
        <div role="alert" className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          {submitError}
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Model</CardTitle>
          <CardDescription>Name and describe the registered model.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Name</Label>
            <Input
              id="name"
              placeholder="customer-support-lora"
              invalid={Boolean(errors.name)}
              {...register("name")}
            />
            {errors.name ? <p className="text-xs text-destructive">{errors.name.message}</p> : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="description">Description</Label>
            <Input
              id="description"
              placeholder="QLoRA tuned for support replies (optional)"
              invalid={Boolean(errors.description)}
              {...register("description")}
            />
            {errors.description ? (
              <p className="text-xs text-destructive">{errors.description.message}</p>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">First version</CardTitle>
          <CardDescription>Pick a completed training job and the evaluation that validated it.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="training_job_id">Training job</Label>
            <select
              id="training_job_id"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              value={selectedTrainingJobId}
              onChange={(e) => {
                setSelectedTrainingJobId(e.target.value);
                setValue("training_job_id", e.target.value, { shouldValidate: true });
                setValue("evaluation_id", "", { shouldValidate: true });
              }}
              disabled={trainingQuery.isLoading}
            >
              <option value="">
                {trainingQuery.isLoading
                  ? "Loading training jobs…"
                  : eligibleJobs.length === 0
                    ? "No completed training jobs with artifacts"
                    : "Select a training job"}
              </option>
              {eligibleJobs.map((j) => (
                <option key={j.id} value={j.id}>
                  {j.id.slice(0, 8)} · {j.base_model}
                </option>
              ))}
            </select>
            {errors.training_job_id ? (
              <p className="text-xs text-destructive">{errors.training_job_id.message}</p>
            ) : eligibleJobs.length === 0 && !trainingQuery.isLoading ? (
              <p className="text-xs text-muted-foreground">
                No training jobs are eligible. Finish a training run first.
              </p>
            ) : null}
            {trainingJobId ? (
              <p className="font-mono text-xs text-muted-foreground">Selected: {trainingJobId.slice(0, 8)}</p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="evaluation_id">Evaluation</Label>
            <select
              id="evaluation_id"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              {...register("evaluation_id")}
              disabled={evaluationsQuery.isLoading || !selectedTrainingJobId}
            >
              <option value="">
                {!selectedTrainingJobId
                  ? "Choose a training job first"
                  : evaluationsQuery.isLoading
                    ? "Loading evaluations…"
                    : eligibleEvaluations.length === 0
                      ? "No completed evaluations"
                      : "Select an evaluation"}
              </option>
              {eligibleEvaluations.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.id.slice(0, 8)}
                </option>
              ))}
            </select>
            {errors.evaluation_id ? (
              <p className="text-xs text-destructive">{errors.evaluation_id.message}</p>
            ) : null}
            {evaluationId ? (
              <p className="font-mono text-xs text-muted-foreground">Selected: {evaluationId.slice(0, 8)}</p>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button type="submit" disabled={isPending}>
          {isPending ? <Spinner size="sm" label="Registering" /> : "Register model"}
        </Button>
      </div>
    </form>
  );
}
