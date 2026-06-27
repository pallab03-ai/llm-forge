import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type MetricCardProps = {
  label: string;
  description?: string;
  value: number | null | undefined;
  formatValue: (value: number) => string;
  isLoading: boolean;
  hasError: boolean;
};

export function MetricCard({
  label,
  description,
  value,
  formatValue,
  isLoading,
  hasError,
}: MetricCardProps) {
  const showDash = hasError || value === null || value === undefined;
  const showSkeleton = isLoading && !showDash;

  return (
    <Card className="h-full">
      <CardHeader className="space-y-1 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
        {description ? <CardDescription className="text-xs">{description}</CardDescription> : null}
      </CardHeader>
      <CardContent>
        <p
          className={cn(
            "text-2xl font-semibold tabular-nums",
            showDash ? "text-muted-foreground" : "text-foreground",
          )}
        >
          {showSkeleton ? <Skeleton className="h-7 w-20" /> : showDash ? "—" : formatValue(value as number)}
        </p>
      </CardContent>
    </Card>
  );
}
