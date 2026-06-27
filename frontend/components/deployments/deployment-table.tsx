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
import type { Deployment } from "@/features/deployments/schemas";
import { cn } from "@/lib/utils";

type DeploymentTableProps = {
  deployments: Deployment[];
  isLoading: boolean;
  isError: boolean;
};

function formatDate(value: string): string {
  return new Date(value).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function DeploymentRow({ deployment }: { deployment: Deployment }) {
  return (
    <TableRow>
      <TableCell>
        <Link
          href={`/deployments/${deployment.id}`}
          className="font-medium text-foreground underline-offset-4 hover:underline"
        >
          {deployment.deployment_name}
        </Link>
      </TableCell>
      <TableCell className="font-mono text-xs text-muted-foreground">
        {deployment.endpoint_name}
      </TableCell>
      <TableCell className="font-mono text-xs text-muted-foreground">
        {deployment.model_version_id.slice(0, 8)}
      </TableCell>
      <TableCell>
        <DeploymentStatusBadge status={deployment.status} />
      </TableCell>
      <TableCell className="text-muted-foreground">{formatDate(deployment.created_at)}</TableCell>
      <TableCell className="text-right">
        <Link
          href={`/deployments/${deployment.id}`}
          className={buttonVariants({ variant: "ghost", size: "sm" })}
        >
          View
        </Link>
      </TableCell>
    </TableRow>
  );
}

function SkeletonRow() {
  return (
    <TableRow>
      <TableCell><Skeleton className="h-4 w-32" /></TableCell>
      <TableCell><Skeleton className="h-4 w-28" /></TableCell>
      <TableCell><Skeleton className="h-4 w-12" /></TableCell>
      <TableCell><Skeleton className="h-5 w-20" /></TableCell>
      <TableCell><Skeleton className="h-4 w-28" /></TableCell>
      <TableCell />
    </TableRow>
  );
}

export function DeploymentTable({ deployments, isLoading, isError }: DeploymentTableProps) {
  return (
    <div className={cn("rounded-lg border bg-card shadow-sm")}>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Endpoint</TableHead>
            <TableHead>Model version</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Created</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading ? (
            Array.from({ length: 3 }).map((_, i) => <SkeletonRow key={i} />)
          ) : isError ? (
            <TableRow>
              <TableCell colSpan={6} className="text-center text-sm text-muted-foreground">
                Could not load deployments. Refresh the page to try again.
              </TableCell>
            </TableRow>
          ) : deployments.length === 0 ? (
            <TableRow>
              <TableCell colSpan={6} className="text-center text-sm text-muted-foreground">
                No deployments match your search.
              </TableCell>
            </TableRow>
          ) : (
            deployments.map((d) => <DeploymentRow key={d.id} deployment={d} />)
          )}
        </TableBody>
      </Table>
    </div>
  );
}
