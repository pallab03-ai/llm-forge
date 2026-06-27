"use client";

import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { DeploymentStatusBadge } from "@/components/deployments/deployment-status-badge";
import { HealthBadge } from "./health-badge";
import { useDeploymentHealth } from "@/features/monitoring/queries";
import { useDeployments } from "@/features/deployments/queries";
import { formatTimestamp } from "@/features/monitoring/schemas";
import { cn } from "@/lib/utils";

type MonitoringDeploymentsTableProps = {
  className?: string;
};

function HealthCell({ deploymentId }: { deploymentId: string }) {
  const { data, isLoading, isError } = useDeploymentHealth(deploymentId);

  if (isLoading) {
    return <Skeleton className="h-5 w-20" />;
  }
  if (isError || !data) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }
  return <HealthBadge health={data.health} />;
}

function LastCheckedCell({ deploymentId }: { deploymentId: string }) {
  const { data, isLoading, isError } = useDeploymentHealth(deploymentId);

  if (isLoading) {
    return <Skeleton className="h-4 w-32" />;
  }
  if (isError || !data) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }
  return <span className="text-xs text-muted-foreground">{formatTimestamp(data.last_checked)}</span>;
}

export function MonitoringDeploymentsTable({ className }: MonitoringDeploymentsTableProps) {
  const { data, isLoading, isError } = useDeployments();

  if (isError) {
    return (
      <div className={cn("rounded-lg border bg-card p-6 text-sm text-muted-foreground", className)}>
        Could not load deployments. Refresh the page to try again.
      </div>
    );
  }

  const items = data?.items ?? [];

  return (
    <div className={cn("rounded-lg border bg-card shadow-sm", className)}>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Health</TableHead>
            <TableHead>Last checked</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading ? (
            Array.from({ length: 3 }).map((_, i) => (
              <TableRow key={i}>
                <TableCell><Skeleton className="h-4 w-32" /></TableCell>
                <TableCell><Skeleton className="h-5 w-20" /></TableCell>
                <TableCell><Skeleton className="h-5 w-20" /></TableCell>
                <TableCell><Skeleton className="h-4 w-32" /></TableCell>
                <TableCell />
              </TableRow>
            ))
          ) : items.length === 0 ? (
            <TableRow>
              <TableCell colSpan={5} className="text-center text-sm text-muted-foreground">
                No deployments yet. Create a deployment to start collecting health and traffic data.
              </TableCell>
            </TableRow>
          ) : (
            items.map((d) => (
              <TableRow key={d.id}>
                <TableCell>
                  <Link
                    href={`/monitoring/${d.id}`}
                    className="font-medium text-foreground underline-offset-4 hover:underline"
                  >
                    {d.deployment_name}
                  </Link>
                </TableCell>
                <TableCell>
                  <DeploymentStatusBadge status={d.status} />
                </TableCell>
                <TableCell>
                  <HealthCell deploymentId={d.id} />
                </TableCell>
                <TableCell>
                  <LastCheckedCell deploymentId={d.id} />
                </TableCell>
                <TableCell className="text-right">
                  <Link
                    href={`/monitoring/${d.id}`}
                    className={buttonVariants({ variant: "ghost", size: "sm" })}
                  >
                    View monitoring
                  </Link>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  );
}
