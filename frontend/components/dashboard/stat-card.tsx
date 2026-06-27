import Link from "next/link";
import * as React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type StatCardProps = {
  icon: React.ReactNode;
  label: string;
  count: number | null;
  description: string;
  href: string;
  isLoading: boolean;
  hasError: boolean;
};

const numberFormatter = new Intl.NumberFormat();

export function StatCard({ icon, label, count, description, href, isLoading, hasError }: StatCardProps) {
  return (
    <Link
      href={href}
      aria-label={`${label}: ${hasError ? "unavailable" : isLoading ? "loading" : numberFormatter.format(count ?? 0)}. ${description}.`}
      className="group block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background rounded-lg"
    >
      <Card className="h-full transition-colors group-hover:bg-accent/30">
        <CardContent className="flex h-full flex-col gap-3 p-5">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-muted-foreground">{label}</span>
            <span className="text-muted-foreground transition-colors group-hover:text-foreground" aria-hidden>
              {icon}
            </span>
          </div>
          <div className={cn("text-3xl font-semibold tracking-tight tabular-nums")}>
            {isLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : hasError ? (
              <span className="text-muted-foreground">—</span>
            ) : (
              numberFormatter.format(count ?? 0)
            )}
          </div>
          <p className="text-xs text-muted-foreground">{description}</p>
        </CardContent>
      </Card>
    </Link>
  );
}
