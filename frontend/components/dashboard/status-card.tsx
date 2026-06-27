import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export type Status = "operational" | "degraded" | "unknown";

type StatusCardProps = {
  label: string;
  status: Status;
  detail?: string;
};

const labelMap: Record<Status, string> = {
  operational: "Operational",
  degraded: "Degraded",
  unknown: "Unknown",
};

const dotMap: Record<Status, string> = {
  operational: "bg-emerald-500",
  degraded: "bg-amber-500",
  unknown: "bg-muted-foreground/50",
};

export function StatusCard({ label, status, detail }: StatusCardProps) {
  return (
    <Card>
      <CardContent className="flex items-center justify-between gap-3 p-4">
        <div className="min-w-0 space-y-0.5">
          <p className="text-sm font-medium leading-none">{label}</p>
          {detail ? <p className="truncate text-xs text-muted-foreground">{detail}</p> : null}
        </div>
        <div className="flex flex-shrink-0 items-center gap-2">
          <span className={cn("h-2 w-2 rounded-full", dotMap[status])} aria-hidden />
          <span className="text-xs font-medium text-muted-foreground">{labelMap[status]}</span>
        </div>
      </CardContent>
    </Card>
  );
}
