"use client";

import { Cpu, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { TrainingTable } from "@/components/training/training-table";
import { useTrainingJobs } from "@/features/training/queries";

export default function TrainingPage() {
  const { data, isLoading, isError } = useTrainingJobs();
  const [query, setQuery] = useState("");

  const jobs = useMemo(() => data?.items ?? [], [data]);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return jobs;
    return jobs.filter(
      (j) =>
        j.base_model.toLowerCase().includes(q) ||
        j.id.toLowerCase().includes(q) ||
        j.training_type.toLowerCase().includes(q),
    );
  }, [jobs, query]);

  return (
    <div className="space-y-8">
      <PageHeader
        title="Training"
        description="Configure and monitor QLoRA fine-tuning jobs."
        actions={
          <Link href="/training/new" className={buttonVariants()}>
            <Plus className="h-4 w-4" />
            New training job
          </Link>
        }
      />

      {isError ? (
        <EmptyState
          icon={<Cpu className="h-6 w-6" aria-hidden />}
          title="Could not load training jobs"
          description="Check your connection and refresh the page. Existing jobs are safe."
        />
      ) : jobs.length === 0 && !isLoading ? (
        <EmptyState
          icon={<Cpu className="h-8 w-8" aria-hidden />}
          title="No training jobs yet"
          description="Create your first training job to start fine-tuning a model on one of your datasets."
          action={
            <Link href="/training/new" className={buttonVariants()}>
              <Plus className="h-4 w-4" />
              New training job
            </Link>
          }
        />
      ) : (
        <>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative w-full sm:max-w-sm">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search by model, id, or method…"
                className="pl-9"
                aria-label="Search training jobs"
              />
            </div>
            <p className="text-xs text-muted-foreground" aria-live="polite">
              {filtered.length === jobs.length
                ? `${jobs.length} job${jobs.length === 1 ? "" : "s"}`
                : `${filtered.length} of ${jobs.length} match`}
            </p>
          </div>

          <TrainingTable jobs={filtered} isLoading={isLoading} isError={false} />
        </>
      )}
    </div>
  );
}
