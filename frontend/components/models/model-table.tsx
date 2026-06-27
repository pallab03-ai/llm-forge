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
import { RegistryStatusBadge } from "@/components/models/registry-status-badge";
import { headVersion, type Model } from "@/features/models/schemas";
import { cn } from "@/lib/utils";

type ModelTableProps = {
  models: Model[];
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

function ModelRow({ model }: { model: Model }) {
  const head = headVersion(model);
  return (
    <TableRow>
      <TableCell>
        <Link
          href={`/models/${model.id}`}
          className="font-medium text-foreground underline-offset-4 hover:underline"
        >
          {model.name}
        </Link>
      </TableCell>
      <TableCell className="font-mono text-xs text-muted-foreground">
        {head ? `v${head.version_number}` : "—"}
      </TableCell>
      <TableCell>
        {head ? <RegistryStatusBadge status={head.status} /> : <span className="text-muted-foreground">—</span>}
      </TableCell>
      <TableCell className="text-muted-foreground">{formatDate(model.created_at)}</TableCell>
      <TableCell className="text-right">
        <Link href={`/models/${model.id}`} className={buttonVariants({ variant: "ghost", size: "sm" })}>
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
      <TableCell><Skeleton className="h-4 w-12" /></TableCell>
      <TableCell><Skeleton className="h-5 w-20" /></TableCell>
      <TableCell><Skeleton className="h-4 w-28" /></TableCell>
      <TableCell />
    </TableRow>
  );
}

export function ModelTable({ models, isLoading, isError }: ModelTableProps) {
  return (
    <div className={cn("rounded-lg border bg-card shadow-sm")}>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Model</TableHead>
            <TableHead>Version</TableHead>
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
              <TableCell colSpan={5} className="text-center text-sm text-muted-foreground">
                Could not load models. Refresh the page to try again.
              </TableCell>
            </TableRow>
          ) : models.length === 0 ? (
            <TableRow>
              <TableCell colSpan={5} className="text-center text-sm text-muted-foreground">
                No models match your search.
              </TableCell>
            </TableRow>
          ) : (
            models.map((m) => <ModelRow key={m.id} model={m} />)
          )}
        </TableBody>
      </Table>
    </div>
  );
}
