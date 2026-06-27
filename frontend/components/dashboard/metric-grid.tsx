import * as React from "react";
import { cn } from "@/lib/utils";

type MetricGridProps = React.HTMLAttributes<HTMLDivElement>;

export function MetricGrid({ className, children, ...props }: MetricGridProps) {
  return (
    <div
      className={cn("grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4", className)}
      {...props}
    >
      {children}
    </div>
  );
}
