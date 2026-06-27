"use client";

import { Upload } from "lucide-react";
import { useId, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { DATASET_MAX_UPLOAD_HINT, MAX_UPLOAD_BYTES, type DatasetFormat, datasetFormatValues } from "@/features/datasets/schemas";

type DatasetUploadZoneProps = {
  file: File | null;
  onFile: (file: File | null) => void;
  disabled?: boolean;
};

function detectFormat(name: string): DatasetFormat | null {
  const lower = name.toLowerCase();
  if (lower.endsWith(".csv")) return "csv";
  if (lower.endsWith(".jsonl")) return "jsonl";
  if (lower.endsWith(".json")) return "json";
  return null;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function DatasetUploadZone({ file, onFile, disabled }: DatasetUploadZoneProps) {
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();

  function accept(file: File): string | null {
    if (!detectFormat(file.name)) {
      return "Unsupported file type. Use CSV, JSON, or JSONL.";
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      return `File is ${formatBytes(file.size)} which exceeds the ${DATASET_MAX_UPLOAD_HINT} limit.`;
    }
    return null;
  }

  function setFile(next: File | null) {
    if (!next) {
      onFile(null);
      setError(null);
      return;
    }
    const err = accept(next);
    if (err) {
      setError(err);
      onFile(null);
      return;
    }
    setError(null);
    onFile(next);
  }

  return (
    <div className="space-y-2">
      <button
        type="button"
        id={inputId}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          if (disabled) return;
          const dropped = e.dataTransfer.files[0];
          if (dropped) setFile(dropped);
        }}
        disabled={disabled}
        className={cn(
          "flex w-full flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed bg-card/40 p-10 text-center transition-colors",
          "hover:bg-accent/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
          dragOver && "border-primary bg-accent/40",
          disabled && "pointer-events-none opacity-50",
        )}
        aria-describedby={`${inputId}-help`}
        data-testid="upload-zone"
      >
        <span className="rounded-full bg-muted p-3 text-muted-foreground" aria-hidden>
          <Upload className="h-5 w-5" />
        </span>
        <div className="space-y-1">
          <p className="text-sm font-medium">
            {file ? file.name : "Drop a file here or click to choose"}
          </p>
          <p className="text-xs text-muted-foreground">
            CSV, JSON, or JSONL · up to {DATASET_MAX_UPLOAD_HINT}
          </p>
        </div>
        {file ? (
          <p className="text-xs text-muted-foreground">
            {formatBytes(file.size)} · {detectFormat(file.name)?.toUpperCase()}
          </p>
        ) : null}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={datasetFormatValues.map((f) => (f === "jsonl" ? ".jsonl" : `.${f}`)).join(",")}
        className="sr-only"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        disabled={disabled}
        aria-hidden
        tabIndex={-1}
      />
      <p id={`${inputId}-help`} className="text-xs text-muted-foreground">
        {error ? <span className="text-destructive">{error}</span> : "Files are validated by the server after upload."}
      </p>
    </div>
  );
}
