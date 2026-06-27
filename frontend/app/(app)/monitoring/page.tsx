"use client";

import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  CircleSlash,
  Clock,
  Rocket,
  Timer,
} from "lucide-react";
import { useMemo } from "react";
import { DashboardCard } from "@/components/monitoring/dashboard-card";
import { MonitoringDeploymentsTable } from "@/components/monitoring/monitoring-deployments-table";
import { Card, CardContent } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { SectionHeader } from "@/components/ui/section-header";
import { useMonitoringDashboard } from "@/features/monitoring/queries";
import {
  formatCount,
  formatLatencyMs,
  formatPercentage,
  type DashboardData,
} from "@/features/monitoring/schemas";

type CardSpec = {
  key: keyof DashboardData;
  label: string;
  description: string;
  format: (value: number) => string;
  icon: React.ReactNode;
};

const CARD_SPECS: CardSpec[] = [
  { key: "deployment_count", label: "Total deployments", description: "Deployments you own", format: formatCount, icon: <Rocket className="h-4 w-4" aria-hidden /> },
  { key: "active_deployments", label: "Active deployments", description: "Currently serving inference", format: formatCount, icon: <Activity className="h-4 w-4" aria-hidden /> },
  { key: "failed_deployments", label: "Failed deployments", description: "In FAILED status", format: formatCount, icon: <AlertTriangle className="h-4 w-4" aria-hidden /> },
  { key: "total_requests", label: "Total requests", description: "Lifetime inference calls", format: formatCount, icon: <CheckCircle2 className="h-4 w-4" aria-hidden /> },
  { key: "success_rate", label: "Success rate", description: "Share of successful requests", format: formatPercentage, icon: <CircleSlash className="h-4 w-4" aria-hidden /> },
  { key: "average_latency_ms", label: "Average latency", description: "Mean end-to-end latency", format: formatLatencyMs, icon: <Timer className="h-4 w-4" aria-hidden /> },
];

export default function MonitoringPage() {
  const { data, isLoading, isError } = useMonitoringDashboard();
  const values = useMemo(() => data ?? null, [data]);

  return (
    <div className="space-y-8">
      <PageHeader
        title="Monitoring"
        description="Real-time health, traffic, and error data for your deployments."
        actions={
          <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            <Clock className="h-3.5 w-3.5" aria-hidden />
            Refreshes every 30 s
          </span>
        }
      />

      <section aria-labelledby="metrics-heading" className="space-y-3">
        <SectionHeader title="Workspace metrics" description="Aggregated across your deployments" id="metrics-heading" />
        {isError ? (
          <Card>
            <CardContent className="p-6 text-sm text-muted-foreground">
              Could not load monitoring dashboard. Check your connection and refresh the page.
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {CARD_SPECS.map((spec) => (
              <DashboardCard
                key={spec.key}
                label={spec.label}
                value={values ? values[spec.key] : null}
                description={spec.description}
                formatValue={spec.format}
                isLoading={isLoading}
                hasError={isError}
                icon={spec.icon}
              />
            ))}
          </div>
        )}
      </section>

      <section aria-labelledby="deployments-heading" className="space-y-3">
        <SectionHeader
          title="Deployments"
          description="Per-deployment health and last health check timestamp"
          id="deployments-heading"
        />
        <MonitoringDeploymentsTable />
      </section>
    </div>
  );
}
