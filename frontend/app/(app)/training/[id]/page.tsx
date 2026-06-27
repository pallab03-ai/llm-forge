"use client";

import { ArrowLeft, Cpu, RefreshCw, X } from "lucide-react";
import Link from "next/link";
import { use } from "react";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { TrainingConfigCard } from "@/components/training/training-config-card";
import { TrainingSectionEmpty } from "@/components/training/training-section-empty";
import { TrainingStatusBadge } from "@/components/training/training-status-badge";
import {
  TRAINING_TYPE_LABELS,
  isActiveStatus,
} from "@/features/training/schemas";
import { useCancelTrainingJob, useTrainingJob } from "@/features/training/queries";
import { ApiError } from "@/services/api-client";

type TrainingDetailPageProps = {
  params: Promise<{ id: string }>;
};

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function InfoRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <div className="flex items-start justify-between gap-3 py-2 text-sm">
        <span className="text-muted-foreground">{label}</span>
        <span className="text-right">{children}</span>
      </div>
      <Separator />
    </>
  );
}

export default function TrainingDetailPage({ params }: TrainingDetailPageProps) {
  const { id } = use(params);
  const { data, isLoading, isError, error, isFetching } = useTrainingJob(id);
  const cancel = useCancelTrainingJob();

  if (isError) {
    const isNotFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="space-y-6">
        <Link href="/training" className={buttonVariants({ variant: "ghost", size: "sm" })}>
          <ArrowLeft className="h-4 w-4" />
          All training jobs
        </Link>
        <EmptyState
          icon={<Cpu className="h-6 w-6" aria-hidden />}
          title={isNotFound ? "Training job not found" : "Could not load training job"}
          description={
            isNotFound
              ? "This job may have been cancelled, deleted, or you do not have access."
              : "Check your connection and try again."
          }
        />
      </div>
    );
  }

  if (isLoading || !data) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-9 w-40" />
        <Skeleton className="h-20 w-full" />
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <Skeleton className="h-72 lg:col-span-1" />
          <div className="space-y-6 lg:col-span-2">
            <Skeleton className="h-64" />
            <Skeleton className="h-48" />
            <Skeleton className="h-48" />
            <Skeleton className="h-48" />
          </div>
        </div>
      </div>
    );
  }

  const isActive = isActiveStatus(data.status);

  return (
    <div className="space-y-6">
      <Link href="/training" className={buttonVariants({ variant: "ghost", size: "sm" })}>
        <ArrowLeft className="h-4 w-4" />
        All training jobs
      </Link>

      <header className="flex flex-col gap-3 border-b pb-6 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
              Training job <span className="font-mono text-base text-muted-foreground">{data.id.slice(0, 8)}</span>
            </h1>
            <TrainingStatusBadge status={data.status} />
            {isFetching ? <Spinner size="sm" label="Refreshing" /> : null}
          </div>
          <p className="text-sm text-muted-foreground font-mono">{data.base_model}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {isActive ? (
            <button
              type="button"
              onClick={() => cancel.mutate(data.id)}
              disabled={cancel.isPending}
              className={buttonVariants({ variant: "outline" })}
            >
              {cancel.isPending ? <Spinner size="sm" /> : <X className="h-4 w-4" />}
              Cancel job
            </button>
          ) : (
            <button
              type="button"
              className={buttonVariants({ variant: "outline" })}
              onClick={() => window.location.reload()}
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          )}
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-1">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Job information</CardTitle>
              <CardDescription>Identity, status, and timestamps.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-1">
              <InfoRow label="ID"><span className="font-mono text-xs">{data.id}</span></InfoRow>
              <InfoRow label="Method">{TRAINING_TYPE_LABELS[data.training_type]}</InfoRow>
              <InfoRow label="Base model"><span className="font-mono text-xs">{data.base_model}</span></InfoRow>
              <InfoRow label="Dataset"><span className="font-mono text-xs">{data.dataset_id.slice(0, 8)}</span></InfoRow>
              <InfoRow label="Dataset version"><span className="font-mono text-xs">{data.dataset_version_id.slice(0, 8)}</span></InfoRow>
              <InfoRow label="Created">{formatDateTime(data.created_at)}</InfoRow>
              <InfoRow label="Started">{formatDateTime(data.started_at)}</InfoRow>
              <InfoRow label="Completed">{formatDateTime(data.completed_at)}</InfoRow>
              {data.error_message ? (
                <>
                  <InfoRow label="Error">
                    <span className="max-w-xs text-destructive">{data.error_message}</span>
                  </InfoRow>
                </>
              ) : null}
            </CardContent>
          </Card>

          <TrainingConfigCard job={data} />
        </div>

        <div className="space-y-6 lg:col-span-2">
          <TrainingSectionEmpty kind="metrics" jobStatus={data.status} />
          <TrainingSectionEmpty kind="logs" jobStatus={data.status} />
          <TrainingSectionEmpty
            kind="artifacts"
            jobStatus={data.status}
            artifactPath={data.artifact_path}
          />
        </div>
      </div>
    </div>
  );
}
