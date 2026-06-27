import Link from "next/link";
import { Database } from "lucide-react";
import { Badge } from "@/components/ui/badge";
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
import { FORMAT_LABELS, type DatasetItem, type DatasetStatus } from "@/features/datasets/schemas";
import { cn } from "@/lib/utils";

type DatasetTableProps = {
  datasets: DatasetItem[];
  isLoading: boolean;
  isError: boolean;
};

const statusVariant: Record<DatasetStatus, "default" | "success" | "warning" | "danger" | "secondary"> = {
  uploading: "warning",
  validating: "warning",
  ready: "success",
  failed: "danger",
  deleted: "secondary",
};

const statusLabel: Record<DatasetStatus, string> = {
  uploading: "Uploading",
  validating: "Validating",
  ready: "Ready",
  failed: "Failed",
  deleted: "Deleted",
};

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function DatasetRow({ dataset }: { dataset: DatasetItem }) {
  return (
    <TableRow>
      <TableCell>
        <Link
          href={`/datasets/${dataset.id}`}
          className="font-medium text-foreground underline-offset-4 hover:underline"
        >
          {dataset.name}
        </Link>
        {dataset.description ? (
          <p className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">{dataset.description}</p>
        ) : null}
      </TableCell>
      <TableCell>
        <Badge variant="outline">{FORMAT_LABELS[dataset.format]}</Badge>
      </TableCell>
      <TableCell className="text-muted-foreground">—</TableCell>
      <TableCell className="text-muted-foreground">—</TableCell>
      <TableCell>
        <Badge variant={statusVariant[dataset.status]}>{statusLabel[dataset.status]}</Badge>
      </TableCell>
      <TableCell className="text-muted-foreground">{formatDate(dataset.created_at)}</TableCell>
      <TableCell className="text-right">
        <Link href={`/datasets/${dataset.id}`} className={buttonVariants({ variant: "ghost", size: "sm" })}>
          View
        </Link>
      </TableCell>
    </TableRow>
  );
}

function SkeletonRow() {
  return (
    <TableRow>
      <TableCell><Skeleton className="h-4 w-40" /></TableCell>
      <TableCell><Skeleton className="h-4 w-12" /></TableCell>
      <TableCell><Skeleton className="h-4 w-10" /></TableCell>
      <TableCell><Skeleton className="h-4 w-10" /></TableCell>
      <TableCell><Skeleton className="h-4 w-16" /></TableCell>
      <TableCell><Skeleton className="h-4 w-24" /></TableCell>
      <TableCell />
    </TableRow>
  );
}

export function DatasetTable({ datasets, isLoading, isError }: DatasetTableProps) {
  return (
    <div className={cn("rounded-lg border bg-card shadow-sm")}>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Format</TableHead>
            <TableHead>Records</TableHead>
            <TableHead>Versions</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Created</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading ? (
            Array.from({ length: 4 }).map((_, i) => <SkeletonRow key={i} />)
          ) : isError ? (
            <TableRow>
              <TableCell colSpan={7} className="text-center text-sm text-muted-foreground">
                <Database className="mx-auto mb-2 h-5 w-5" aria-hidden />
                Could not load datasets. Refresh the page to try again.
              </TableCell>
            </TableRow>
          ) : datasets.length === 0 ? (
            <TableRow>
              <TableCell colSpan={7} className="text-center text-sm text-muted-foreground">
                No datasets match your search.
              </TableCell>
            </TableRow>
          ) : (
            datasets.map((d) => <DatasetRow key={d.id} dataset={d} />)
          )}
        </TableBody>
      </Table>
    </div>
  );
}
