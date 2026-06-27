import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError } from "@/services/api-client";
import { formatTimestamp, type ErrorLogItem } from "@/features/monitoring/schemas";

type ErrorTableProps = {
  items: ErrorLogItem[];
  isLoading: boolean;
  isError: boolean;
  error?: unknown;
};

export function ErrorTable({ items, isLoading, isError, error }: ErrorTableProps) {
  if (isError) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="rounded-lg border bg-card p-6 text-sm text-muted-foreground">
        {notFound
          ? "Deployment not found. It may have been removed or you do not have access."
          : "Could not load recent errors. Refresh the page to try again."}
      </div>
    );
  }

  return (
    <div className="rounded-lg border bg-card shadow-sm">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Timestamp</TableHead>
            <TableHead>Error type</TableHead>
            <TableHead>Message</TableHead>
            <TableHead className="text-right">Status code</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading ? (
            Array.from({ length: 3 }).map((_, i) => (
              <TableRow key={i}>
                <TableCell><Skeleton className="h-4 w-40" /></TableCell>
                <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                <TableCell><Skeleton className="h-4 w-56" /></TableCell>
                <TableCell><Skeleton className="ml-auto h-4 w-12" /></TableCell>
              </TableRow>
            ))
          ) : items.length === 0 ? (
            <TableRow>
              <TableCell colSpan={4} className="text-center text-sm text-muted-foreground">
                No errors recorded for this deployment yet.
              </TableCell>
            </TableRow>
          ) : (
            items.map((e, i) => (
              <TableRow key={`${e.timestamp}-${i}`}>
                <TableCell className="text-muted-foreground">{formatTimestamp(e.timestamp)}</TableCell>
                <TableCell>
                  <span className="font-mono text-xs">{e.error_type}</span>
                </TableCell>
                <TableCell className="text-sm">{e.message}</TableCell>
                <TableCell className="text-right tabular-nums">{e.status_code}</TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  );
}
