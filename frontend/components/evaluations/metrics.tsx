import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  METRICS,
  formatMetricValue,
  type MetricField,
} from "@/features/evaluations/schemas";
import { cn } from "@/lib/utils";

type MetricsGridProps = {
  // ponytail: accept a values dict (not the whole Evaluation) so the model
  // registry page can reuse this component for `ModelVersion.metrics_snapshot`
  // without a duplicate component. Both the Evaluation and ModelVersion
  // shapes expose the same 5 metric fields.
  values: Partial<Record<MetricField, number | null>>;
};

type MetricCardProps = {
  label: string;
  description: string;
  value: number | null | undefined;
};

function MetricCard({ label, description, value }: MetricCardProps) {
  const isReady = value !== null && value !== undefined;
  return (
    <Card className="h-full">
      <CardHeader className="space-y-1 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
        <CardDescription className="text-xs">{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <p
          className={cn(
            "text-2xl font-semibold tabular-nums",
            isReady ? "text-foreground" : "text-muted-foreground",
          )}
        >
          {formatMetricValue(value ?? null)}
        </p>
      </CardContent>
    </Card>
  );
}

export function MetricsGrid({ values }: MetricsGridProps) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {METRICS.map((metric) => (
        <MetricCard
          key={metric.field}
          label={metric.label}
          description={metric.description}
          value={values[metric.field]}
        />
      ))}
    </div>
  );
}
