"use client";

import { Database, FlaskConical, Gauge, Layers, Rocket } from "lucide-react";
import { useMemo } from "react";
import { ActivityTimeline } from "@/components/dashboard/activity-timeline";
import { MetricGrid } from "@/components/dashboard/metric-grid";
import { QuickActionCard } from "@/components/dashboard/quick-action-card";
import { StatCard } from "@/components/dashboard/stat-card";
import { StatusCard, type Status } from "@/components/dashboard/status-card";
import { Card, CardContent } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { SectionHeader } from "@/components/ui/section-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useDashboardData } from "@/hooks/use-dashboard-data";

function greetingForHour(hour: number): string {
  if (hour < 5) return "Working late";
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function formatDate(date: Date): string {
  return date.toLocaleDateString(undefined, {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

function pickStatus(value: string | undefined): Status {
  if (!value) return "unknown";
  const v = value.toLowerCase();
  if (v === "healthy" || v === "ok" || v === "operational") return "operational";
  if (v === "degraded" || v === "warning") return "degraded";
  return "unknown";
}

export default function DashboardPage() {
  const data = useDashboardData();
  const { user, datasets, trainingJobs, evaluations, models, deployments, health } = data;

  const now = useMemo(() => new Date(), []);
  const greeting = useMemo(() => greetingForHour(now.getHours()), [now]);
  const date = useMemo(() => formatDate(now), [now]);

  const apiStatus: Status = health.isError || !health.data ? "unknown" : pickStatus(health.data.status);
  const authStatus: Status = user ? "operational" : "unknown";

  return (
    <div className="space-y-8">
      <PageHeader
        title="Dashboard"
        description="Operational overview of your datasets, training jobs, and deployments."
      />

      <section aria-labelledby="welcome-heading" className="rounded-lg border bg-card/40 p-6 sm:p-8">
        <div className="space-y-2">
          <h2 id="welcome-heading" className="text-2xl font-semibold tracking-tight sm:text-3xl">
            {greeting}, <span className="text-primary">{user?.username ?? "there"}</span>
          </h2>
          <p className="text-sm text-muted-foreground sm:text-base">
            Ready to train your next model?
          </p>
          <p className="pt-2 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">{user?.role === "admin" ? "Administrator" : "Member"}</span>
            <span aria-hidden> · </span>
            <span>{date}</span>
          </p>
        </div>
      </section>

      <section aria-labelledby="stats-heading" className="space-y-3">
        <SectionHeader title="Quick statistics" description="Counts across your workspace" id="stats-heading" />
        <MetricGrid>
          <StatCard
            icon={<Database className="h-4 w-4" aria-hidden />}
            label="Datasets"
            count={datasets.data ?? null}
            description="Uploaded datasets"
            href="/datasets"
            isLoading={datasets.isLoading}
            hasError={datasets.isError}
          />
          <StatCard
            icon={<FlaskConical className="h-4 w-4" aria-hidden />}
            label="Training jobs"
            count={trainingJobs.data ?? null}
            description="All training jobs"
            href="/training"
            isLoading={trainingJobs.isLoading}
            hasError={trainingJobs.isError}
          />
          <StatCard
            icon={<Gauge className="h-4 w-4" aria-hidden />}
            label="Evaluations"
            count={evaluations.data ?? null}
            description="Evaluation runs"
            href="/evaluations"
            isLoading={evaluations.isLoading}
            hasError={evaluations.isError}
          />
          <StatCard
            icon={<Layers className="h-4 w-4" aria-hidden />}
            label="Registered models"
            count={models.data ?? null}
            description="Models in the registry"
            href="/models"
            isLoading={models.isLoading}
            hasError={models.isError}
          />
        </MetricGrid>
        <MetricGrid className="lg:grid-cols-4">
          <StatCard
            icon={<Rocket className="h-4 w-4" aria-hidden />}
            label="Deployments"
            count={deployments.data ?? null}
            description="Active deployments"
            href="/deployments"
            isLoading={deployments.isLoading}
            hasError={deployments.isError}
          />
        </MetricGrid>
      </section>

      <section aria-labelledby="actions-heading" className="space-y-3">
        <SectionHeader title="Quick actions" description="Jump to the most common workflows" id="actions-heading" />
        <MetricGrid className="sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          <QuickActionCard
            icon={<Database className="h-4 w-4" aria-hidden />}
            title="Upload dataset"
            description="Bring your own training data into the workspace."
            href="/datasets"
            cta="Upload"
          />
          <QuickActionCard
            icon={<FlaskConical className="h-4 w-4" aria-hidden />}
            title="Create training job"
            description="Start a fine-tuning run on a base model."
            href="/training"
            cta="Create"
          />
          <QuickActionCard
            icon={<Gauge className="h-4 w-4" aria-hidden />}
            title="Run evaluation"
            description="Score a model on ROUGE, BERTScore, and more."
            href="/evaluations"
            cta="Run"
          />
          <QuickActionCard
            icon={<Layers className="h-4 w-4" aria-hidden />}
            title="Register model"
            description="Promote a trained checkpoint into the registry."
            href="/models"
            cta="Register"
          />
          <QuickActionCard
            icon={<Rocket className="h-4 w-4" aria-hidden />}
            title="Deploy model"
            description="Generate a deployment endpoint for inference."
            href="/deployments"
            cta="Deploy"
          />
        </MetricGrid>
      </section>

      <section aria-labelledby="activity-heading" className="space-y-3">
        <SectionHeader title="Recent activity" description="Latest events across your workspace" id="activity-heading" />
        <ActivityTimeline items={[]} />
      </section>

      <section aria-labelledby="status-heading" className="space-y-3">
        <SectionHeader title="System status" description="Service health snapshot" id="status-heading" />
        <MetricGrid className="sm:grid-cols-2 lg:grid-cols-3">
          {health.isLoading ? (
            <Card>
              <CardContent className="p-4">
                <Skeleton className="h-5 w-32" />
                <Skeleton className="mt-2 h-3 w-20" />
              </CardContent>
            </Card>
          ) : (
            <StatusCard
              label="API"
              status={apiStatus}
              detail={health.data ? `v${health.data.version ?? "?"} · ${health.data.environment ?? ""}`.trim() : undefined}
            />
          )}
          <StatusCard label="Authentication" status={authStatus} detail={user ? `Signed in as ${user.email}` : undefined} />
          <StatusCard label="Deployment service" status="unknown" detail="Status endpoint not exposed" />
          <StatusCard label="Database" status="unknown" detail="Status endpoint not exposed" />
          <StatusCard label="GPU" status="unknown" detail="Status endpoint not exposed" />
        </MetricGrid>
      </section>
    </div>
  );
}
