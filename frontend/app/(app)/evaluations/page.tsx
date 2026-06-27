"use client";

import { FlaskConical, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { EvaluationTable } from "@/components/evaluations/evaluation-table";
import { useEvaluations } from "@/features/evaluations/queries";

export default function EvaluationsPage() {
  const { data, isLoading, isError } = useEvaluations();
  const [query, setQuery] = useState("");

  const evaluations = useMemo(() => data?.items ?? [], [data]);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return evaluations;
    return evaluations.filter(
      (e) =>
        e.id.toLowerCase().includes(q) ||
        e.model_id.toLowerCase().includes(q) ||
        e.dataset_id.toLowerCase().includes(q) ||
        e.status.toLowerCase().includes(q),
    );
  }, [evaluations, query]);

  return (
    <div className="space-y-8">
      <PageHeader
        title="Evaluations"
        description="Run ROUGE, BERTScore, and semantic similarity evaluations against your datasets."
        actions={
          <Link href="/evaluations/new" className={buttonVariants()}>
            <Plus className="h-4 w-4" />
            New evaluation
          </Link>
        }
      />

      {isError ? (
        <EmptyState
          icon={<FlaskConical className="h-6 w-6" aria-hidden />}
          title="Could not load evaluations"
          description="Check your connection and refresh the page. Existing evaluations are safe."
        />
      ) : evaluations.length === 0 && !isLoading ? (
        <EmptyState
          icon={<FlaskConical className="h-8 w-8" aria-hidden />}
          title="No evaluations yet"
          description="Run your first evaluation to compare a fine-tuned model against a dataset version."
          action={
            <Link href="/evaluations/new" className={buttonVariants()}>
              <Plus className="h-4 w-4" />
              New evaluation
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
                placeholder="Search by id, model, or dataset…"
                className="pl-9"
                aria-label="Search evaluations"
              />
            </div>
            <p className="text-xs text-muted-foreground" aria-live="polite">
              {filtered.length === evaluations.length
                ? `${evaluations.length} evaluation${evaluations.length === 1 ? "" : "s"}`
                : `${filtered.length} of ${evaluations.length} match`}
            </p>
          </div>

          <EvaluationTable evaluations={filtered} isLoading={isLoading} isError={false} />
        </>
      )}
    </div>
  );
}
