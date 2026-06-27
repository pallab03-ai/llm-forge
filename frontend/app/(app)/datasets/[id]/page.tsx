"use client";

import { Database } from "lucide-react";
import { use } from "react";
import { DatasetHeader } from "@/components/datasets/dataset-header";
import { MetadataCard } from "@/components/datasets/metadata-card";
import { ValidationSummary } from "@/components/datasets/validation-summary";
import { VersionTable } from "@/components/datasets/version-table";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useDataset } from "@/features/datasets/queries";
import { ApiError } from "@/services/api-client";
import Link from "next/link";

type DatasetDetailPageProps = {
  params: Promise<{ id: string }>;
};

export default function DatasetDetailPage({ params }: DatasetDetailPageProps) {
  const { id } = use(params);
  const { data, isLoading, isError, error } = useDataset(id);

  if (isError) {
    const isNotFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="space-y-6">
        <EmptyState
          icon={<Database className="h-6 w-6" aria-hidden />}
          title={isNotFound ? "Dataset not found" : "Could not load dataset"}
          description={
            isNotFound
              ? "This dataset may have been deleted or you do not have access."
              : "Check your connection and try again."
          }
          action={
            <Link href="/datasets" className={buttonVariants({ variant: "outline" })}>
              Back to datasets
            </Link>
          }
        />
      </div>
    );
  }

  if (isLoading || !data) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-9 w-32" />
        <Skeleton className="h-16 w-full" />
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <Skeleton className="h-96 lg:col-span-1" />
          <div className="space-y-6 lg:col-span-2">
            <Skeleton className="h-64" />
            <Skeleton className="h-64" />
          </div>
        </div>
      </div>
    );
  }

  const versions = data.versions ?? [];
  const latest = versions[0] ?? null;

  return (
    <div className="space-y-6">
      <DatasetHeader dataset={data} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-1">
          <MetadataCard dataset={data} latest={latest} />
        </div>

        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Versions</CardTitle>
              <CardDescription>
                {versions.length === 0
                  ? "No versions yet."
                  : `${versions.length} version${versions.length === 1 ? "" : "s"}, newest first.`}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <VersionTable
                versions={versions}
                isLoading={false}
                latestVersion={latest?.version_number ?? null}
              />
            </CardContent>
          </Card>

          <ValidationSummary rawJson={latest?.validation_errors ?? null} />

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Metadata</CardTitle>
              <CardDescription>Raw dataset fields returned by the backend.</CardDescription>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-muted-foreground">ID</dt>
                  <dd className="font-mono text-xs">{data.id}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Created</dt>
                  <dd>{new Date(data.created_at).toLocaleString()}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Updated</dt>
                  <dd>{new Date(data.updated_at).toLocaleString()}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Owner</dt>
                  <dd className="font-mono text-xs">{data.created_by ?? "—"}</dd>
                </div>
              </dl>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
