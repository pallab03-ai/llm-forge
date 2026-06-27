import * as React from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type DashboardCardProps = {
  label: string;
  value: number | null;
  description: string;
  formatValue: (value: number) => string;
  isLoading: boolean;
  hasError: boolean;
  icon?: React.ReactNode;
};

export function DashboardCard({
  label,
  value,
  description,
  formatValue,
  isLoading,
  hasError,
  icon,
}: DashboardCardProps) {
  const showSkeleton = isLoading;
  const showDash = hasError || value === null;

  return (
    <Card className="h-full">
      <CardHeader className="flex flex-row items-start justify-between gap-2 space-y-0 pb-2">
        <div className="space-y-1">
          <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
          <CardDescription className="text-xs">{description}</CardDescription>
        </div>
        {icon ? (
          <span className="text-muted-foreground" aria-hidden>
            {icon}
          </span>
        ) : null}
      </CardHeader>
      <CardContent>
        <p
          aria-label={
            showSkeleton
              ? `${label}: loading.`
              : showDash
                ? `${label}: unavailable.`
                : `${label}: ${formatValue(value ?? 0)}.`
          }
          className={cn(
            "text-3xl font-semibold tracking-tight tabular-nums",
            showDash ? "text-muted-foreground" : "text-foreground",
          )}
        >
          {showSkeleton ? <Skeleton className="h-9 w-24" /> : showDash ? "—" : formatValue(value ?? 0)}
        </p>
      </CardContent>
    </Card>
  );
}
