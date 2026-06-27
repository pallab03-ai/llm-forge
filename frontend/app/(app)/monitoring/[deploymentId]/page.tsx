"use client";

import { ArrowLeft, Rocket } from "lucide-react";
import Link from "next/link";
import { Suspense, use, useMemo, useState } from "react";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { ErrorTable } from "@/components/monitoring/error-table";
import { HealthCard } from "@/components/monitoring/health-card";
import { MetricsGrid } from "@/components/monitoring/metrics-grid";
import { Pagination } from "@/components/monitoring/pagination";
import { RequestTable } from "@/components/monitoring/request-table";
import { DeploymentStatusBadge } from "@/components/deployments/deployment-status-badge";
import {
  useDeployment,
} from "@/features/deployments/queries";
import type { Deployment } from "@/features/deployments/schemas";
import {
  useDeploymentErrors,
  useDeploymentHealth,
  useDeploymentMetrics,
  useDeploymentRequests,
} from "@/features/monitoring/queries";
import {
  ERRORS_PAGE_SIZE,
  REQUESTS_PAGE_SIZE,
  formatCount,
  formatLatencyMs,
  formatPercentage,
  formatTimestamp,
} from "@/features/monitoring/schemas";
import { ApiError } from "@/services/api-client";

type DeploymentMonitoringPageProps = {
  params: Promise<{ deploymentId: string }>;
};

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

function DeploymentInfoCard({ deployment }: { deployment: Deployment }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Deployment information</CardTitle>
        <CardDescription>Identity, endpoint, and timestamps.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-1">
        <InfoRow label="ID"><span className="font-mono text-xs">{deployment.id}</span></InfoRow>
        <InfoRow label="Deployment name">{deployment.deployment_name}</InfoRow>
        <InfoRow label="Endpoint name">
          <span className="font-mono text-xs">{deployment.endpoint_name}</span>
        </InfoRow>
        <InfoRow label="Model version">
          <span className="font-mono text-xs">{deployment.model_version_id}</span>
        </InfoRow>
        <InfoRow label="Owner">
          <span className="font-mono text-xs">{deployment.owner_id}</span>
        </InfoRow>
        <InfoRow label="Created">{formatTimestamp(deployment.created_at)}</InfoRow>
        <InfoRow label="Updated">{formatTimestamp(deployment.updated_at)}</InfoRow>
      </CardContent>
    </Card>
  );
}

function useRequestPage(deploymentId: string) {
  const [page, setPage] = useState(0);
  const offset = page * REQUESTS_PAGE_SIZE;
  const query = useDeploymentRequests(deploymentId, { limit: REQUESTS_PAGE_SIZE, offset });
  const goTo = (next: { limit: number; offset: number }) => {
    setPage(Math.floor(next.offset / next.limit));
  };
  return { ...query, page, goTo };
}

function useErrorPage(deploymentId: string) {
  const [page, setPage] = useState(0);
  const offset = page * ERRORS_PAGE_SIZE;
  const query = useDeploymentErrors(deploymentId, { limit: ERRORS_PAGE_SIZE, offset });
  const goTo = (next: { limit: number; offset: number }) => {
    setPage(Math.floor(next.offset / next.limit));
  };
  return { ...query, page, goTo };
}

function MonitoringDetailContent({ deploymentId }: { deploymentId: string }) {
  const { data, isLoading, isError, error, isFetching } = useDeployment(deploymentId);
  const health = useDeploymentHealth(deploymentId);
  const metrics = useDeploymentMetrics(deploymentId);
  const requests = useRequestPage(deploymentId);
  const errors = useErrorPage(deploymentId);

  if (isError) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="space-y-6">
        <Link href="/monitoring" className={buttonVariants({ variant: "ghost", size: "sm" })}>
          <ArrowLeft className="h-4 w-4" />
          All monitoring
        </Link>
        <EmptyState
          icon={<Rocket className="h-6 w-6" aria-hidden />}
          title={notFound ? "Deployment not found" : "Could not load deployment"}
          description={
            notFound
              ? "This deployment may have been removed or you do not have access."
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
            <Skeleton className="h-48" />
            <Skeleton className="h-48" />
            <Skeleton className="h-72" />
            <Skeleton className="h-72" />
          </div>
        </div>
      </div>
    );
  }

  const metricsItems = metrics.data
    ? [
        { key: "request_count", label: "Request count", description: "Lifetime requests for this deployment", value: metrics.data.request_count, formatValue: formatCount },
        { key: "success_count", label: "Success count", description: "Requests completed without error", value: metrics.data.success_count, formatValue: formatCount },
        { key: "failure_count", label: "Failure count", description: "Requests that ended in error", value: metrics.data.failure_count, formatValue: formatCount },
        { key: "success_rate", label: "Success rate", description: "Successes as a share of total", value: metrics.data.request_count === 0 ? 0 : metrics.data.success_count / metrics.data.request_count, formatValue: formatPercentage },
        { key: "average_latency_ms", label: "Average latency", description: "Mean end-to-end latency", value: metrics.data.average_latency_ms, formatValue: formatLatencyMs },
        { key: "min_latency_ms", label: "Minimum latency", description: "Fastest recorded request", value: metrics.data.min_latency_ms, formatValue: formatLatencyMs },
        { key: "max_latency_ms", label: "Maximum latency", description: "Slowest recorded request", value: metrics.data.max_latency_ms, formatValue: formatLatencyMs },
      ]
    : [];

  return (
    <div className="space-y-6">
      <Link href="/monitoring" className={buttonVariants({ variant: "ghost", size: "sm" })}>
        <ArrowLeft className="h-4 w-4" />
        All monitoring
      </Link>

      <header className="flex flex-col gap-3 border-b pb-6 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{data.deployment_name}</h1>
            <DeploymentStatusBadge status={data.status} />
            {isFetching ? <Spinner size="sm" label="Refreshing" /> : null}
          </div>
          <p className="text-sm text-muted-foreground">
            Endpoint <span className="font-mono">{data.endpoint_name}</span>
            {" · "}
            Model version <span className="font-mono">{data.model_version_id.slice(0, 8)}</span>
          </p>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-1">
          <DeploymentInfoCard deployment={data} />
        </div>

        <div className="space-y-6 lg:col-span-2">
          <HealthCard
            data={health.data}
            isLoading={health.isLoading}
            isError={health.isError}
            error={health.error}
          />

          <section aria-labelledby="metrics-section" className="space-y-3">
            <h2 id="metrics-section" className="text-lg font-semibold tracking-tight">
              Metrics
            </h2>
            {metrics.isError ? (
              <Card>
                <CardContent className="p-6 text-sm text-muted-foreground">
                  Could not load metrics. Check your connection and try again.
                </CardContent>
              </Card>
            ) : (
              <MetricsGrid
                items={metricsItems}
                isLoading={metrics.isLoading}
                hasError={metrics.isError}
              />
            )}
          </section>

          <section aria-labelledby="requests-section" className="space-y-3">
            <div className="flex items-end justify-between gap-3">
              <h2 id="requests-section" className="text-lg font-semibold tracking-tight">
                Recent requests
              </h2>
              <p className="text-xs text-muted-foreground">
                Newest first · metadata only (no prompt or response content)
              </p>
            </div>
            <RequestTable
              items={requests.data?.items ?? []}
              isLoading={requests.isLoading}
              isError={requests.isError}
              error={requests.error}
            />
            {requests.data && requests.data.total > REQUESTS_PAGE_SIZE ? (
              <Pagination
                total={requests.data.total}
                limit={REQUESTS_PAGE_SIZE}
                offset={requests.data.offset}
                onChange={requests.goTo}
              />
            ) : null}
          </section>

          <section aria-labelledby="errors-section" className="space-y-3">
            <div className="flex items-end justify-between gap-3">
              <h2 id="errors-section" className="text-lg font-semibold tracking-tight">
                Recent errors
              </h2>
              <p className="text-xs text-muted-foreground">
                Only failed requests are surfaced here
              </p>
            </div>
            <ErrorTable
              items={errors.data?.items ?? []}
              isLoading={errors.isLoading}
              isError={errors.isError}
              error={errors.error}
            />
            {errors.data && errors.data.total > ERRORS_PAGE_SIZE ? (
              <Pagination
                total={errors.data.total}
                limit={ERRORS_PAGE_SIZE}
                offset={errors.data.offset}
                onChange={errors.goTo}
              />
            ) : null}
          </section>
        </div>
      </div>
    </div>
  );
}

export default function DeploymentMonitoringPage({ params }: DeploymentMonitoringPageProps) {
  const { deploymentId } = use(params);
  const stableId = useMemo(() => deploymentId, [deploymentId]);
  return (
    <Suspense
      fallback={
        <div className="space-y-6">
          <Skeleton className="h-9 w-40" />
          <Skeleton className="h-20 w-full" />
        </div>
      }
    >
      <MonitoringDetailContent deploymentId={stableId} />
    </Suspense>
  );
}
