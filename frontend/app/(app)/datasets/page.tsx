"use client";

import { Database, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { DatasetCard } from "@/components/datasets/dataset-card";
import { DatasetTable } from "@/components/datasets/dataset-table";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { useDatasets } from "@/features/datasets/queries";

export default function DatasetsPage() {
  const { data, isLoading, isError } = useDatasets();
  const [query, setQuery] = useState("");

  const datasets = useMemo(() => data?.items ?? [], [data]);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return datasets;
    return datasets.filter((d) => d.name.toLowerCase().includes(q));
  }, [datasets, query]);

  return (
    <div className="space-y-8">
      <PageHeader
        title="Datasets"
        description="Upload, version, and manage training datasets."
        actions={
          <Link href="/datasets/upload" className={buttonVariants()}>
            <Plus className="h-4 w-4" />
            Upload dataset
          </Link>
        }
      />

      {isError ? (
        <EmptyState
          icon={<Database className="h-6 w-6" aria-hidden />}
          title="Could not load datasets"
          description="Check your connection and refresh the page. Your existing datasets are safe."
        />
      ) : datasets.length === 0 && !isLoading ? (
        <EmptyState
          icon={<Database className="h-8 w-8" aria-hidden />}
          title="No datasets yet"
          description="Upload your first CSV, JSON, or JSONL file to start training models."
          action={
            <Link href="/datasets/upload" className={buttonVariants()}>
              <Plus className="h-4 w-4" />
              Upload dataset
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
                placeholder="Search by name…"
                className="pl-9"
                aria-label="Search datasets by name"
              />
            </div>
            <p className="text-xs text-muted-foreground" aria-live="polite">
              {filtered.length === datasets.length
                ? `${datasets.length} dataset${datasets.length === 1 ? "" : "s"}`
                : `${filtered.length} of ${datasets.length} match`}
            </p>
          </div>

          <DatasetTable datasets={filtered} isLoading={isLoading} isError={false} />

          {datasets.length > 0 ? (
            <section aria-labelledby="example-heading" className="space-y-3">
              <h2 id="example-heading" className="text-sm font-semibold tracking-tight text-muted-foreground">
                Recent
              </h2>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {datasets.slice(0, 3).map((d) => (
                  <DatasetCard key={d.id} dataset={d} href={`/datasets/${d.id}`} />
                ))}
              </div>
            </section>
          ) : null}
        </>
      )}
    </div>
  );
}
