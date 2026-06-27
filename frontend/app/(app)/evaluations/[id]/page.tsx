"use client";

import { ArrowLeft, FlaskConical, RefreshCw } from "lucide-react";
import Link from "next/link";
import { use } from "react";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { EvaluationSectionEmpty } from "@/components/evaluations/evaluation-section-empty";
import { EvaluationStatusBadge } from "@/components/evaluations/evaluation-status-badge";
import { MetricsGrid } from "@/components/evaluations/metrics";
import {
  METRICS,
  isActiveEvaluationStatus,
  type Evaluation,
} from "@/features/evaluations/schemas";
import { useEvaluation } from "@/features/evaluations/queries";
import { ApiError } from "@/services/api-client";

type EvaluationDetailPageProps = {
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

function Summary({ evaluation }: { evaluation: Evaluation }) {
  const computed = METRICS.filter((m) => evaluation[m.field] !== null).length;
  const total = METRICS.length;

  // ponytail: derive a one-line summary from timestamps + metric count. The
  // backend exposes no `summary` field, so the page composes one from the
  // fields it already has rather than fabricating a value.
  let body: string;
  if (evaluation.status === "completed") {
    if (evaluation.started_at && evaluation.completed_at) {
      const seconds = Math.max(
        0,
        Math.round(
          (new Date(evaluation.completed_at).getTime() -
            new Date(evaluation.started_at).getTime()) /
            1000,
        ),
      );
      body = `Completed in ${seconds}s with ${computed} of ${total} metrics.`;
    } else {
      body = `Completed with ${computed} of ${total} metrics.`;
    }
  } else if (evaluation.status === "failed") {
    body = "Evaluation failed. See the error message above.";
  } else if (evaluation.status === "running") {
    body = "Evaluation is running. This page polls every 2 seconds.";
  } else {
    body = "Evaluation is queued and will start when a worker is available.";
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Summary</CardTitle>
        <CardDescription>{body}</CardDescription>
      </CardHeader>
    </Card>
  );
}

export default function EvaluationDetailPage({ params }: EvaluationDetailPageProps) {
  const { id } = use(params);
  const { data, isLoading, isError, error, isFetching } = useEvaluation(id);

  if (isError) {
    const isNotFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="space-y-6">
        <Link href="/evaluations" className={buttonVariants({ variant: "ghost", size: "sm" })}>
          <ArrowLeft className="h-4 w-4" />
          All evaluations
        </Link>
        <EmptyState
          icon={<FlaskConical className="h-6 w-6" aria-hidden />}
          title={isNotFound ? "Evaluation not found" : "Could not load evaluation"}
          description={
            isNotFound
              ? "This evaluation may have been removed or you do not have access."
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
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
        </div>
        <Skeleton className="h-32" />
      </div>
    );
  }

  const isActive = isActiveEvaluationStatus(data.status);

  return (
    <div className="space-y-6">
      <Link href="/evaluations" className={buttonVariants({ variant: "ghost", size: "sm" })}>
        <ArrowLeft className="h-4 w-4" />
        All evaluations
      </Link>

      <header className="flex flex-col gap-3 border-b pb-6 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
              Evaluation <span className="font-mono text-base text-muted-foreground">{data.id.slice(0, 8)}</span>
            </h1>
            <EvaluationStatusBadge status={data.status} />
            {isFetching ? <Spinner size="sm" label="Refreshing" /> : null}
          </div>
          <p className="text-sm text-muted-foreground">
            Model <span className="font-mono">{data.model_id.slice(0, 8)}</span>
            {" · "}
            Dataset <span className="font-mono">{data.dataset_id.slice(0, 8)}</span>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {isActive ? (
            <button
              type="button"
              className={buttonVariants({ variant: "outline" })}
              onClick={() => window.location.reload()}
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
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
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="text-base">Evaluation information</CardTitle>
            <CardDescription>Identity, status, and timestamps.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-1">
            <InfoRow label="ID"><span className="font-mono text-xs">{data.id}</span></InfoRow>
            <InfoRow label="Status"><EvaluationStatusBadge status={data.status} /></InfoRow>
            <InfoRow label="Model"><span className="font-mono text-xs">{data.model_id}</span></InfoRow>
            <InfoRow label="Dataset"><span className="font-mono text-xs">{data.dataset_id}</span></InfoRow>
            <InfoRow label="Dataset version"><span className="font-mono text-xs">{data.dataset_version_id}</span></InfoRow>
            <InfoRow label="Created">{formatDateTime(data.created_at)}</InfoRow>
            <InfoRow label="Started">{formatDateTime(data.started_at)}</InfoRow>
            <InfoRow label="Completed">{formatDateTime(data.completed_at)}</InfoRow>
            {data.error_message ? (
              <InfoRow label="Error">
                <span className="max-w-xs text-destructive">{data.error_message}</span>
              </InfoRow>
            ) : null}
          </CardContent>
        </Card>

        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Metrics</CardTitle>
              <CardDescription>
                Five metric fields the backend computes: ROUGE-L, BERTScore (precision, recall, F1), and semantic similarity.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <MetricsGrid values={data} />
            </CardContent>
          </Card>

          <Summary evaluation={data} />

          <EvaluationSectionEmpty kind="raw-results" evaluationStatus={data.status} />
          <EvaluationSectionEmpty kind="comparison" evaluationStatus={data.status} />
        </div>
      </div>
    </div>
  );
}
