"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { useModels } from "@/features/models/queries";
import {
  createDeploymentSchema,
  type CreateDeploymentInput,
} from "@/features/deployments/schemas";
import { useCreateDeployment } from "@/features/deployments/queries";
import { ApiError } from "@/services/api-client";

const DEFAULTS: CreateDeploymentInput = {
  model_version_id: "",
  deployment_name: "",
  endpoint_name: "",
};

type VersionOption = {
  id: string;
  label: string;
};

export function DeploymentForm() {
  const router = useRouter();
  const modelsQuery = useModels();
  const createDeployment = useCreateDeployment();

  // ponytail: backend rejects deployment of an archived model version with
  // 409 (MODEL_VERSION_ARCHIVED). The client filter mirrors that single
  // rule. Draft and staging are allowed — the backend does not enforce
  // production-only.
  const eligibleVersions = useMemo<VersionOption[]>(() => {
    const items = modelsQuery.data?.items ?? [];
    const opts: VersionOption[] = [];
    for (const model of items) {
      for (const v of model.versions) {
        if (v.status === "archived") continue;
        opts.push({
          id: v.id,
          label: `${model.name} · v${v.version_number} · ${v.status}`,
        });
      }
    }
    return opts;
  }, [modelsQuery.data]);

  const form = useForm<CreateDeploymentInput>({
    resolver: zodResolver(createDeploymentSchema),
    defaultValues: DEFAULTS,
  });
  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = form;

  const selectedVersionId = watch("model_version_id");
  const [submitError, setSubmitError] = useState<string | null>(null);

  const noEligible =
    !modelsQuery.isLoading && !modelsQuery.isError && eligibleVersions.length === 0;

  const onSubmit = handleSubmit(async (values) => {
    setSubmitError(null);
    try {
      const deployment = await createDeployment.mutateAsync(values);
      toast.success("Deployment created.");
      router.push(`/deployments/${deployment.id}`);
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
          <CardTitle className="text-base">Model version</CardTitle>
          <CardDescription>Pick a non-archived model version to deploy.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <Label htmlFor="model_version_id">Model version</Label>
          <select
            id="model_version_id"
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            value={selectedVersionId}
            onChange={(e) =>
              setValue("model_version_id", e.target.value, { shouldValidate: true })
            }
            disabled={modelsQuery.isLoading}
          >
            <option value="">
              {modelsQuery.isLoading
                ? "Loading model versions…"
                : noEligible
                  ? "No eligible model versions"
                  : "Select a model version"}
            </option>
            {eligibleVersions.map((v) => (
              <option key={v.id} value={v.id}>
                {v.label}
              </option>
            ))}
          </select>
          {errors.model_version_id ? (
            <p className="text-xs text-destructive">{errors.model_version_id.message}</p>
          ) : noEligible ? (
            <p className="text-xs text-muted-foreground">
              Register a model version in the Models page before creating a deployment.
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Deployment</CardTitle>
          <CardDescription>Name the deployment and its endpoint.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="deployment_name">Deployment name</Label>
            <Input
              id="deployment_name"
              placeholder="customer-support-bot"
              invalid={Boolean(errors.deployment_name)}
              {...register("deployment_name")}
            />
            {errors.deployment_name ? (
              <p className="text-xs text-destructive">{errors.deployment_name.message}</p>
            ) : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="endpoint_name">Endpoint name</Label>
            <Input
              id="endpoint_name"
              placeholder="customer-support-bot-v1"
              invalid={Boolean(errors.endpoint_name)}
              {...register("endpoint_name")}
            />
            {errors.endpoint_name ? (
              <p className="text-xs text-destructive">{errors.endpoint_name.message}</p>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button type="submit" disabled={createDeployment.isPending || noEligible}>
          {createDeployment.isPending ? <Spinner size="sm" label="Creating" /> : "Create deployment"}
        </Button>
      </div>
    </form>
  );
}
