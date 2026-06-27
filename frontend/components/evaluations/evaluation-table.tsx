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
import { EvaluationStatusBadge } from "@/components/evaluations/evaluation-status-badge";
import { METRICS, type Evaluation } from "@/features/evaluations/schemas";
import { cn } from "@/lib/utils";

type EvaluationTableProps = {
  evaluations: Evaluation[];
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

function hasAnyMetric(evaluation: Evaluation): boolean {
  return METRICS.some((m) => evaluation[m.field] !== null);
}

function EvaluationRow({ evaluation }: { evaluation: Evaluation }) {
  return (
    <TableRow>
      <TableCell>
        <Link
          href={`/evaluations/${evaluation.id}`}
          className="font-medium text-foreground underline-offset-4 hover:underline"
        >
          {evaluation.id.slice(0, 8)}
        </Link>
      </TableCell>
      <TableCell className="max-w-[16ch] truncate font-mono text-xs text-muted-foreground">
        {evaluation.model_id.slice(0, 8)}
      </TableCell>
      <TableCell className="font-mono text-xs text-muted-foreground">
        {evaluation.dataset_id.slice(0, 8)}
      </TableCell>
      <TableCell>
        <EvaluationStatusBadge status={evaluation.status} />
      </TableCell>
      <TableCell className="text-muted-foreground">{formatDate(evaluation.created_at)}</TableCell>
      <TableCell className="text-muted-foreground">
        {hasAnyMetric(evaluation) ? "Available" : "—"}
      </TableCell>
      <TableCell className="text-right">
        <Link
          href={`/evaluations/${evaluation.id}`}
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
      <TableCell><Skeleton className="h-4 w-20" /></TableCell>
      <TableCell><Skeleton className="h-4 w-20" /></TableCell>
      <TableCell><Skeleton className="h-4 w-20" /></TableCell>
      <TableCell><Skeleton className="h-5 w-20" /></TableCell>
      <TableCell><Skeleton className="h-4 w-28" /></TableCell>
      <TableCell><Skeleton className="h-4 w-16" /></TableCell>
      <TableCell />
    </TableRow>
  );
}

export function EvaluationTable({ evaluations, isLoading, isError }: EvaluationTableProps) {
  return (
    <div className={cn("rounded-lg border bg-card shadow-sm")}>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Evaluation</TableHead>
            <TableHead>Model</TableHead>
            <TableHead>Dataset</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Created</TableHead>
            <TableHead>Metrics</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading ? (
            Array.from({ length: 3 }).map((_, i) => <SkeletonRow key={i} />)
          ) : isError ? (
            <TableRow>
              <TableCell colSpan={7} className="text-center text-sm text-muted-foreground">
                Could not load evaluations. Refresh the page to try again.
              </TableCell>
            </TableRow>
          ) : evaluations.length === 0 ? (
            <TableRow>
              <TableCell colSpan={7} className="text-center text-sm text-muted-foreground">
                No evaluations match your search.
              </TableCell>
            </TableRow>
          ) : (
            evaluations.map((e) => <EvaluationRow key={e.id} evaluation={e} />)
          )}
        </TableBody>
      </Table>
    </div>
  );
}
