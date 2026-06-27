"use client";

import { CheckCircle2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

type UploadProgressProps = {
  fileName: string;
  loaded: number;
  total: number;
  status: "uploading" | "success" | "error";
  errorMessage?: string;
  onCancel?: () => void;
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function UploadProgress({ fileName, loaded, total, status, errorMessage, onCancel }: UploadProgressProps) {
  const percent = total > 0 ? Math.min(100, Math.round((loaded / total) * 100)) : 0;

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "rounded-lg border bg-card p-4 shadow-sm",
        status === "error" && "border-destructive/40",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <p className="truncate text-sm font-medium">{fileName}</p>
          <p className="text-xs text-muted-foreground">
            {status === "uploading" && `${formatBytes(loaded)} of ${formatBytes(total)} · ${percent}%`}
            {status === "success" && "Upload complete. Finalising…"}
            {status === "error" && (errorMessage ?? "Upload failed.")}
          </p>
        </div>
        <div className="flex flex-shrink-0 items-center gap-2">
          {status === "uploading" ? <Spinner size="sm" /> : null}
          {status === "success" ? (
            <CheckCircle2 className="h-5 w-5 text-emerald-500" aria-hidden />
          ) : null}
          {status === "uploading" && onCancel ? (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={onCancel}
              aria-label="Cancel upload"
            >
              <X className="h-4 w-4" />
            </Button>
          ) : null}
        </div>
      </div>
      <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            "h-full rounded-full transition-all",
            status === "error" ? "bg-destructive" : "bg-primary",
          )}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}
