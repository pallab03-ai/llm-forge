import { Archive, Rocket } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { RegistryStatusBadge } from "@/components/models/registry-status-badge";
import { useArchiveVersion, usePromoteVersion } from "@/features/models/queries";
import type { ModelVersion } from "@/features/models/schemas";
import { cn } from "@/lib/utils";

type VersionTableProps = {
  modelId: string;
  versions: ModelVersion[];
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

function VersionRow({ modelId, version }: { modelId: string; version: ModelVersion }) {
  const promote = usePromoteVersion(modelId);
  const archive = useArchiveVersion(modelId);

  const canPromote = version.status !== "production" && version.status !== "archived";
  const canArchive = version.status !== "archived";

  return (
    <tr className="border-b transition-colors hover:bg-muted/50">
      <td className="p-3 align-middle font-mono text-sm">v{version.version_number}</td>
      <td className="p-3 align-middle">
        <RegistryStatusBadge status={version.status} />
      </td>
      <td className="p-3 align-middle font-mono text-xs text-muted-foreground">
        {version.training_job_id.slice(0, 8)}
      </td>
      <td className="p-3 align-middle font-mono text-xs text-muted-foreground">
        {version.evaluation_id.slice(0, 8)}
      </td>
      <td className="p-3 align-middle text-xs text-muted-foreground">
        {formatDate(version.created_at)}
      </td>
      <td className="p-3 align-middle text-right">
        <div className="flex flex-wrap items-center justify-end gap-2">
          {canPromote ? (
            <button
              type="button"
              onClick={() => promote.mutate(version.id)}
              disabled={promote.isPending}
              className={cn(buttonVariants({ variant: "outline", size: "sm" }))}
            >
              {promote.isPending ? <Spinner size="sm" /> : <Rocket className="h-3.5 w-3.5" />}
              Promote
            </button>
          ) : null}
          {canArchive ? (
            <button
              type="button"
              onClick={() => archive.mutate(version.id)}
              disabled={archive.isPending}
              className={cn(buttonVariants({ variant: "outline", size: "sm" }))}
            >
              {archive.isPending ? <Spinner size="sm" /> : <Archive className="h-3.5 w-3.5" />}
              Archive
            </button>
          ) : null}
        </div>
      </td>
    </tr>
  );
}

export function VersionTable({ modelId, versions }: VersionTableProps) {
  return (
    <div className={cn("rounded-lg border bg-card shadow-sm")}>
      <table className="w-full caption-bottom text-sm">
        <thead className="[&_tr]:border-b">
          <tr>
            <th className="h-10 px-3 text-left align-middle font-medium text-muted-foreground">Version</th>
            <th className="h-10 px-3 text-left align-middle font-medium text-muted-foreground">Status</th>
            <th className="h-10 px-3 text-left align-middle font-medium text-muted-foreground">Training</th>
            <th className="h-10 px-3 text-left align-middle font-medium text-muted-foreground">Evaluation</th>
            <th className="h-10 px-3 text-left align-middle font-medium text-muted-foreground">Created</th>
            <th className="h-10 px-3 text-right align-middle font-medium text-muted-foreground">Actions</th>
          </tr>
        </thead>
        <tbody className="[&_tr:last-child]:border-0">
          {versions.map((v) => (
            <VersionRow key={v.id} modelId={modelId} version={v} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
