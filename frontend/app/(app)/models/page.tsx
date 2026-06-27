"use client";

import { Plus, Search, Sparkles } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { ModelTable } from "@/components/models/model-table";
import { useModels } from "@/features/models/queries";

export default function ModelsPage() {
  const { data, isLoading, isError } = useModels();
  const [query, setQuery] = useState("");

  const models = useMemo(() => data?.items ?? [], [data]);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return models;
    return models.filter(
      (m) =>
        m.name.toLowerCase().includes(q) ||
        (m.description ?? "").toLowerCase().includes(q) ||
        m.id.toLowerCase().includes(q),
    );
  }, [models, query]);

  return (
    <div className="space-y-8">
      <PageHeader
        title="Models"
        description="Registry of fine-tuned models with version history and promotion workflow."
        actions={
          <Link href="/models/register" className={buttonVariants()}>
            <Plus className="h-4 w-4" />
            Register model
          </Link>
        }
      />

      {isError ? (
        <EmptyState
          icon={<Sparkles className="h-6 w-6" aria-hidden />}
          title="Could not load models"
          description="Check your connection and refresh the page. Existing models are safe."
        />
      ) : models.length === 0 && !isLoading ? (
        <EmptyState
          icon={<Sparkles className="h-8 w-8" aria-hidden />}
          title="No registered models yet"
          description="Register a completed training run and its evaluation to make the adapter versioned and promotable."
          action={
            <Link href="/models/register" className={buttonVariants()}>
              <Plus className="h-4 w-4" />
              Register model
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
                placeholder="Search by name or description…"
                className="pl-9"
                aria-label="Search models"
              />
            </div>
            <p className="text-xs text-muted-foreground" aria-live="polite">
              {filtered.length === models.length
                ? `${models.length} model${models.length === 1 ? "" : "s"}`
                : `${filtered.length} of ${models.length} match`}
            </p>
          </div>

          <ModelTable models={filtered} isLoading={isLoading} isError={false} />
        </>
      )}
    </div>
  );
}
