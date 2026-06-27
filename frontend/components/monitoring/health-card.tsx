import { Activity, Clock, Rocket } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { DeploymentStatusBadge } from "@/components/deployments/deployment-status-badge";
import { ApiError } from "@/services/api-client";
import { HealthBadge } from "./health-badge";
import { formatTimestamp, type HealthData } from "@/features/monitoring/schemas";

type HealthCardProps = {
  data: HealthData | undefined;
  isLoading: boolean;
  isError: boolean;
  error?: unknown;
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

function notFoundMessage(error: unknown): string | null {
  if (!(error instanceof ApiError)) return null;
  if (error.status === 404) return "Deployment not found. It may have been removed or you do not have access.";
  return null;
}

export function HealthCard({ data, isLoading, isError, error }: HealthCardProps) {
  if (isError) {
    const notFound = notFoundMessage(error);
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Health</CardTitle>
          <CardDescription>
            {notFound ?? "Could not load health. Check your connection and try again."}
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Health</CardTitle>
        <CardDescription>Verdict computed from the most recent inference traffic.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-1">
        {isLoading || !data ? (
          <>
            <InfoRow label="Health"><Skeleton className="h-5 w-20" /></InfoRow>
            <InfoRow label="Message"><Skeleton className="h-4 w-48" /></InfoRow>
            <InfoRow label="Last checked"><Skeleton className="h-4 w-40" /></InfoRow>
            <InfoRow label="Status"><Skeleton className="h-5 w-20" /></InfoRow>
          </>
        ) : (
          <>
            <InfoRow label="Health">
              <span className="inline-flex items-center gap-2">
                <HealthBadge health={data.health} />
              </span>
            </InfoRow>
            <InfoRow label="Message">{data.message}</InfoRow>
            <InfoRow label="Last checked">
              <span className="inline-flex items-center gap-1.5 text-muted-foreground">
                <Clock className="h-3.5 w-3.5" aria-hidden />
                {formatTimestamp(data.last_checked)}
              </span>
            </InfoRow>
            <InfoRow label="Status">
              <span className="inline-flex items-center gap-2">
                {data.status === "active" ? (
                  <Activity className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" aria-hidden />
                ) : (
                  <Rocket className="h-3.5 w-3.5" aria-hidden />
                )}
                <DeploymentStatusBadge status={data.status as "pending" | "deploying" | "active" | "failed"} />
              </span>
            </InfoRow>
          </>
        )}
      </CardContent>
    </Card>
  );
}
