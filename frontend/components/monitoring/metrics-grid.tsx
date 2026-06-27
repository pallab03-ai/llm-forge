import { MetricCard } from "./metric-card";

export type MetricsGridItem = {
  key: string;
  label: string;
  description?: string;
  value: number | null | undefined;
  formatValue: (value: number) => string;
};

type MetricsGridProps = {
  items: MetricsGridItem[];
  isLoading: boolean;
  hasError: boolean;
  className?: string;
};

export function MetricsGrid({ items, isLoading, hasError, className }: MetricsGridProps) {
  return (
    <div className={`grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3${className ? ` ${className}` : ""}`}>
      {items.map((item) => (
        <MetricCard
          key={item.key}
          label={item.label}
          description={item.description}
          value={item.value}
          formatValue={item.formatValue}
          isLoading={isLoading}
          hasError={hasError}
        />
      ))}
    </div>
  );
}
