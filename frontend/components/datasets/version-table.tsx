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
import type { DatasetVersion } from "@/features/datasets/schemas";

type VersionTableProps = {
  versions: DatasetVersion[];
  isLoading: boolean;
  latestVersion: number | null;
};

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function VersionTable({ versions, isLoading, latestVersion }: VersionTableProps) {
  if (isLoading) {
    return (
      <div className="rounded-lg border bg-card shadow-sm">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Version</TableHead>
              <TableHead>Created</TableHead>
              <TableHead>Records</TableHead>
              <TableHead>Size</TableHead>
              <TableHead>Duplicates</TableHead>
              <TableHead className="text-right">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {Array.from({ length: 3 }).map((_, i) => (
              <TableRow key={i}>
                <TableCell><Skeleton className="h-4 w-10" /></TableCell>
                <TableCell><Skeleton className="h-4 w-32" /></TableCell>
                <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                <TableCell />
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    );
  }

  if (versions.length === 0) {
    return (
      <div className="rounded-lg border border-dashed bg-card/40 p-8 text-center text-sm text-muted-foreground">
        No versions yet. Upload a file to create version 1.
      </div>
    );
  }

  return (
    <div className="rounded-lg border bg-card shadow-sm">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Version</TableHead>
            <TableHead>Created</TableHead>
            <TableHead>Records</TableHead>
            <TableHead>Size</TableHead>
            <TableHead>Duplicates</TableHead>
            <TableHead className="text-right">Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {versions.map((v) => {
            const isLatest = latestVersion !== null && v.version_number === latestVersion;
            return (
              <TableRow key={v.id}>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">v{v.version_number}</span>
                    {isLatest ? <Badge variant="info">Latest</Badge> : null}
                  </div>
                </TableCell>
                <TableCell className="text-muted-foreground">{formatDate(v.created_at)}</TableCell>
                <TableCell className="tabular-nums">{v.record_count.toLocaleString()}</TableCell>
                <TableCell className="text-muted-foreground">{formatBytes(v.file_size_bytes)}</TableCell>
                <TableCell className="tabular-nums text-muted-foreground">{v.duplicate_count.toLocaleString()}</TableCell>
                <TableCell className="text-right">
                  {v.validation_errors ? (
                    <Badge variant="warning">Has issues</Badge>
                  ) : (
                    <Badge variant="success">Clean</Badge>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
