import { CheckCircle2, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
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
import { cn } from "@/lib/utils";
import { formatLatencyMs, formatTimestamp, type RequestLogItem } from "@/features/monitoring/schemas";

type RequestTableProps = {
  items: RequestLogItem[];
  isLoading: boolean;
  isError: boolean;
  error?: unknown;
};

function StatusPill({ status }: { status: RequestLogItem["status"] }) {
  if (status === "success") {
    return (
      <Badge variant="success" className="gap-1">
        <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />
        Success
      </Badge>
    );
  }
  return (
    <Badge variant="danger" className="gap-1">
      <XCircle className="h-3.5 w-3.5" aria-hidden />
      Failure
    </Badge>
  );
}

export function RequestTable({ items, isLoading, isError, error }: RequestTableProps) {
  if (isError) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="rounded-lg border bg-card p-6 text-sm text-muted-foreground">
        {notFound
          ? "Deployment not found. It may have been removed or you do not have access."
          : "Could not load recent requests. Refresh the page to try again."}
      </div>
    );
  }

  return (
    <div className="rounded-lg border bg-card shadow-sm">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Timestamp</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Latency</TableHead>
            <TableHead className="text-right">Prompt length</TableHead>
            <TableHead className="text-right">Response length</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading ? (
            Array.from({ length: 3 }).map((_, i) => (
              <TableRow key={i}>
                <TableCell><Skeleton className="h-4 w-40" /></TableCell>
                <TableCell><Skeleton className="h-5 w-20" /></TableCell>
                <TableCell><Skeleton className="ml-auto h-4 w-16" /></TableCell>
                <TableCell><Skeleton className="ml-auto h-4 w-12" /></TableCell>
                <TableCell><Skeleton className="ml-auto h-4 w-12" /></TableCell>
              </TableRow>
            ))
          ) : items.length === 0 ? (
            <TableRow>
              <TableCell colSpan={5} className="text-center text-sm text-muted-foreground">
                No requests recorded for this deployment yet.
              </TableCell>
            </TableRow>
          ) : (
            items.map((r) => (
              <TableRow key={r.id}>
                <TableCell className="text-muted-foreground">{formatTimestamp(r.timestamp)}</TableCell>
                <TableCell>
                  <StatusPill status={r.status} />
                </TableCell>
                <TableCell className={cn("text-right tabular-nums")}>
                  {formatLatencyMs(r.latency_ms)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {r.prompt_length.toLocaleString()}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {r.response_length === null ? "—" : r.response_length.toLocaleString()}
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  );
}
