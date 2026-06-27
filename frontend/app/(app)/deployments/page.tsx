"use client";

import { Plus, Rocket, Search } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { DeploymentTable } from "@/components/deployments/deployment-table";
import { useDeployments } from "@/features/deployments/queries";

export default function DeploymentsPage() {
  const { data, isLoading, isError } = useDeployments();
  const [query, setQuery] = useState("");

  const deployments = useMemo(() => data?.items ?? [], [data]);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return deployments;
    return deployments.filter(
      (d) =>
        d.deployment_name.toLowerCase().includes(q) ||
        d.endpoint_name.toLowerCase().includes(q) ||
        d.id.toLowerCase().includes(q) ||
        d.model_version_id.toLowerCase().includes(q),
    );
  }, [deployments, query]);

  return (
    <div className="space-y-8">
      <PageHeader
        title="Deployments"
        description="Activate and manage inference deployments."
        actions={
          <Link href="/deployments/new" className={buttonVariants()}>
            <Plus className="h-4 w-4" />
            New deployment
          </Link>
        }
      />

      {isError ? (
        <EmptyState
          icon={<Rocket className="h-6 w-6" aria-hidden />}
          title="Could not load deployments"
          description="Check your connection and refresh the page. Existing deployments are safe."
        />
      ) : deployments.length === 0 && !isLoading ? (
        <EmptyState
          icon={<Rocket className="h-8 w-8" aria-hidden />}
          title="No deployments yet"
          description="Pick a non-archived model version and create a deployment to load its adapter."
          action={
            <Link href="/deployments/new" className={buttonVariants()}>
              <Plus className="h-4 w-4" />
              New deployment
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
                placeholder="Search by name, endpoint, or id…"
                className="pl-9"
                aria-label="Search deployments"
              />
            </div>
            <p className="text-xs text-muted-foreground" aria-live="polite">
              {filtered.length === deployments.length
                ? `${deployments.length} deployment${deployments.length === 1 ? "" : "s"}`
                : `${filtered.length} of ${deployments.length} match`}
            </p>
          </div>

          <DeploymentTable deployments={filtered} isLoading={isLoading} isError={false} />
        </>
      )}
    </div>
  );
}
