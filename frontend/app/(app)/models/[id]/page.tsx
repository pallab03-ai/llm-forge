"use client";

import { ArrowLeft, Box, Sparkles } from "lucide-react";
import Link from "next/link";
import { use } from "react";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { MetricsGrid } from "@/components/evaluations/metrics";
import { ModelSectionEmpty } from "@/components/models/model-section-empty";
import { RegistryStatusBadge } from "@/components/models/registry-status-badge";
import { VersionTable } from "@/components/models/version-table";
import { headVersion, type Model } from "@/features/models/schemas";
import { useModel } from "@/features/models/queries";
import { ApiError } from "@/services/api-client";

type ModelDetailPageProps = {
  params: Promise<{ id: string }>;
};

function formatDateTime(value: string | null | undefined): string {
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

function HeadVersionCard({ model }: { model: Model }) {
  const head = headVersion(model);
  if (!head) return <ModelSectionEmpty kind="no-versions" />;

  const hasMetrics = head.metrics_snapshot !== null && Object.keys(head.metrics_snapshot).length > 0;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <CardTitle className="text-base">Latest version</CardTitle>
              <CardDescription>
                v{head.version_number} · registered {formatDateTime(head.created_at)}
              </CardDescription>
            </div>
            <RegistryStatusBadge status={head.status} />
          </div>
        </CardHeader>
        <CardContent className="space-y-1">
          <InfoRow label="Training job">
            <Link
              href={`/training/${head.training_job_id}`}
              className="font-mono text-xs underline-offset-4 hover:underline"
            >
              {head.training_job_id}
            </Link>
          </InfoRow>
          <InfoRow label="Evaluation">
            <Link
              href={`/evaluations/${head.evaluation_id}`}
              className="font-mono text-xs underline-offset-4 hover:underline"
            >
              {head.evaluation_id}
            </Link>
          </InfoRow>
          <InfoRow label="Artifact path">
            <span className="max-w-xs break-all font-mono text-xs">{head.artifact_path}</span>
          </InfoRow>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Evaluation summary</CardTitle>
          <CardDescription>
            Metrics snapshot captured at version registration. Five backend fields.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {hasMetrics ? <MetricsGrid values={head.metrics_snapshot!} /> : <ModelSectionEmpty kind="no-evaluation" />}
        </CardContent>
      </Card>
    </div>
  );
}

function ModelInfoCard({ model }: { model: Model }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Model information</CardTitle>
        <CardDescription>Identity, owner, and timestamps.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-1">
        <InfoRow label="ID"><span className="font-mono text-xs">{model.id}</span></InfoRow>
        <InfoRow label="Name">{model.name}</InfoRow>
        <InfoRow label="Description">
          <span className="max-w-xs text-right">{model.description ?? "—"}</span>
        </InfoRow>
        <InfoRow label="Owner"><span className="font-mono text-xs">{model.owner_id}</span></InfoRow>
        <InfoRow label="Created">{formatDateTime(model.created_at)}</InfoRow>
        <InfoRow label="Updated">{formatDateTime(model.updated_at)}</InfoRow>
        <InfoRow label="Versions">{model.versions.length}</InfoRow>
      </CardContent>
    </Card>
  );
}

function VersionHistoryCard({ model }: { model: Model }) {
  if (model.versions.length === 0) return <ModelSectionEmpty kind="no-versions" />;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Version history</CardTitle>
        <CardDescription>
          All {model.versions.length} version{model.versions.length === 1 ? "" : "s"}, newest first. Promote or archive individual versions.
        </CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        <VersionTable modelId={model.id} versions={model.versions} />
      </CardContent>
    </Card>
  );
}

export default function ModelDetailPage({ params }: ModelDetailPageProps) {
  const { id } = use(params);
  const { data, isLoading, isError, error } = useModel(id);

  if (isError) {
    const isNotFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="space-y-6">
        <Link href="/models" className={buttonVariants({ variant: "ghost", size: "sm" })}>
          <ArrowLeft className="h-4 w-4" />
          All models
        </Link>
        <EmptyState
          icon={<Box className="h-6 w-6" aria-hidden />}
          title={isNotFound ? "Model not found" : "Could not load model"}
          description={
            isNotFound
              ? "This model may have been removed or you do not have access."
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
            <Skeleton className="h-40" />
            <Skeleton className="h-64" />
            <Skeleton className="h-64" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Link href="/models" className={buttonVariants({ variant: "ghost", size: "sm" })}>
        <ArrowLeft className="h-4 w-4" />
        All models
      </Link>

      <header className="flex flex-col gap-3 border-b pb-6 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{data.name}</h1>
            {headVersion(data) ? <RegistryStatusBadge status={headVersion(data)!.status} /> : null}
          </div>
          {data.description ? (
            <p className="text-sm text-muted-foreground">{data.description}</p>
          ) : null}
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-1">
          <ModelInfoCard model={data} />
        </div>

        <div className="space-y-6 lg:col-span-2">
          {data.versions.length === 0 ? (
            <ModelSectionEmpty kind="no-versions" />
          ) : (
            <>
              <HeadVersionCard model={data} />
              <VersionHistoryCard model={data} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
