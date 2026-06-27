"use client";

import { ArrowLeft, Power, Rocket } from "lucide-react";
import Link from "next/link";
import { use, useState } from "react";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { DeploymentPlayground } from "@/components/deployments/deployment-playground";
import { DeploymentStatusBadge } from "@/components/deployments/deployment-status-badge";
import {
  canActivate,
  type Deployment,
} from "@/features/deployments/schemas";
import { useActivateDeployment, useDeployment } from "@/features/deployments/queries";
import { ApiError } from "@/services/api-client";

type DeploymentDetailPageProps = {
  params: Promise<{ id: string }>;
};

function formatDateTime(value: string): string {
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
        <InfoRow label="Created">{formatDateTime(deployment.created_at)}</InfoRow>
        <InfoRow label="Updated">{formatDateTime(deployment.updated_at)}</InfoRow>
      </CardContent>
    </Card>
  );
}

function StatusCard({ deployment }: { deployment: Deployment }) {
  const activate = useActivateDeployment();
  const [error, setError] = useState<string | null>(null);

  const onActivate = async () => {
    setError(null);
    try {
      await activate.mutateAsync(deployment.id);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Network error. Check your connection and try again.");
      }
    }
  };

  let description: string;
  if (deployment.status === "pending") {
    description = "The deployment is created but the adapter has not been loaded yet. Activate to load it.";
  } else if (deployment.status === "deploying") {
    description = "The adapter is loading. This page will refresh when activation completes.";
  } else if (deployment.status === "active") {
    description = "The deployment is active and serving inference requests.";
  } else {
    description = "Activation failed. Re-activate to retry loading the adapter.";
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Status</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center justify-between">
          <DeploymentStatusBadge status={deployment.status} />
        </div>
        {canActivate(deployment.status) ? (
          <button
            type="button"
            onClick={onActivate}
            disabled={activate.isPending}
            className={buttonVariants({ variant: "default", className: "w-full" })}
          >
            {activate.isPending ? <Spinner size="sm" label="Activating" /> : <Power className="h-4 w-4" />}
            Activate
          </button>
        ) : null}
        {error ? (
          <p className="text-xs text-destructive" role="alert">
            {error}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

function EndpointCard({ deployment }: { deployment: Deployment }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Endpoint</CardTitle>
        <CardDescription>Route identifier and model version bound to this deployment.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-1">
        <InfoRow label="Endpoint name">
          <span className="font-mono text-xs">{deployment.endpoint_name}</span>
        </InfoRow>
        <InfoRow label="Model version">
          <span className="font-mono text-xs">{deployment.model_version_id}</span>
        </InfoRow>
      </CardContent>
    </Card>
  );
}

function TimelineCard({ deployment }: { deployment: Deployment }) {
  // ponytail: the backend exposes only created_at and updated_at. There is
  // no separate activated_at / started_at / completed_at. Show what the
  // backend actually returns; "Activated" is shown only when status === active
  // (the updated_at carries the activation timestamp in that case).
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">History</CardTitle>
        <CardDescription>Available deployment timestamps.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-1">
        <InfoRow label="Created">{formatDateTime(deployment.created_at)}</InfoRow>
        <InfoRow label="Updated">{formatDateTime(deployment.updated_at)}</InfoRow>
        {deployment.status === "active" ? (
          <InfoRow label="Activated">
            <span className="text-muted-foreground">Updated at {formatDateTime(deployment.updated_at)}</span>
          </InfoRow>
        ) : null}
      </CardContent>
    </Card>
  );
}

export default function DeploymentDetailPage({ params }: DeploymentDetailPageProps) {
  const { id } = use(params);
  const { data, isLoading, isError, error, isFetching } = useDeployment(id);

  if (isError) {
    const isNotFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="space-y-6">
        <Link href="/deployments" className={buttonVariants({ variant: "ghost", size: "sm" })}>
          <ArrowLeft className="h-4 w-4" />
          All deployments
        </Link>
        <EmptyState
          icon={<Rocket className="h-6 w-6" aria-hidden />}
          title={isNotFound ? "Deployment not found" : "Could not load deployment"}
          description={
            isNotFound
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
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
            <Skeleton className="h-48" />
            <Skeleton className="h-32" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Link href="/deployments" className={buttonVariants({ variant: "ghost", size: "sm" })}>
        <ArrowLeft className="h-4 w-4" />
        All deployments
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
          <StatusCard deployment={data} />
          <EndpointCard deployment={data} />
          <DeploymentPlayground deployment={data} />
          <TimelineCard deployment={data} />
        </div>
      </div>
    </div>
  );
}
