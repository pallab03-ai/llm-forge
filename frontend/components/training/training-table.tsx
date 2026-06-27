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
import { TrainingStatusBadge } from "@/components/training/training-status-badge";
import {
  TRAINING_TYPE_LABELS,
  type TrainingJob,
} from "@/features/training/schemas";
import { cn } from "@/lib/utils";

type TrainingTableProps = {
  jobs: TrainingJob[];
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

function JobRow({ job }: { job: TrainingJob }) {
  return (
    <TableRow>
      <TableCell>
        <Link
          href={`/training/${job.id}`}
          className="font-medium text-foreground underline-offset-4 hover:underline"
        >
          {/* ponytail: backend has no job name field; the id is the only
              stable identifier. */}
          {job.id.slice(0, 8)}
        </Link>
      </TableCell>
      <TableCell className="max-w-[16ch] truncate font-mono text-xs text-muted-foreground">
        {job.base_model}
      </TableCell>
      <TableCell className="font-mono text-xs text-muted-foreground">
        {job.dataset_id.slice(0, 8)}
      </TableCell>
      <TableCell>{TRAINING_TYPE_LABELS[job.training_type]}</TableCell>
      <TableCell>
        <TrainingStatusBadge status={job.status} />
      </TableCell>
      <TableCell className="text-muted-foreground">—</TableCell>
      <TableCell className="text-muted-foreground">{formatDate(job.created_at)}</TableCell>
      <TableCell className="text-right">
        <Link href={`/training/${job.id}`} className={buttonVariants({ variant: "ghost", size: "sm" })}>
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
      <TableCell><Skeleton className="h-4 w-32" /></TableCell>
      <TableCell><Skeleton className="h-4 w-20" /></TableCell>
      <TableCell><Skeleton className="h-4 w-16" /></TableCell>
      <TableCell><Skeleton className="h-5 w-20" /></TableCell>
      <TableCell><Skeleton className="h-4 w-8" /></TableCell>
      <TableCell><Skeleton className="h-4 w-28" /></TableCell>
      <TableCell />
    </TableRow>
  );
}

export function TrainingTable({ jobs, isLoading, isError }: TrainingTableProps) {
  return (
    <div className={cn("rounded-lg border bg-card shadow-sm")}>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Job</TableHead>
            <TableHead>Base model</TableHead>
            <TableHead>Dataset</TableHead>
            <TableHead>Method</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Progress</TableHead>
            <TableHead>Created</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading ? (
            Array.from({ length: 3 }).map((_, i) => <SkeletonRow key={i} />)
          ) : isError ? (
            <TableRow>
              <TableCell colSpan={8} className="text-center text-sm text-muted-foreground">
                Could not load training jobs. Refresh the page to try again.
              </TableCell>
            </TableRow>
          ) : jobs.length === 0 ? (
            <TableRow>
              <TableCell colSpan={8} className="text-center text-sm text-muted-foreground">
                No training jobs match your search.
              </TableCell>
            </TableRow>
          ) : (
            jobs.map((j) => <JobRow key={j.id} job={j} />)
          )}
        </TableBody>
      </Table>
    </div>
  );
}
