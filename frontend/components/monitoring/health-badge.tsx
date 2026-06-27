import { AlertCircle, AlertTriangle, CheckCircle2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  HEALTH_STATE_LABELS,
  HEALTH_STATE_VARIANTS,
  type HealthState,
} from "@/features/monitoring/schemas";
import { cn } from "@/lib/utils";

const healthIcon: Record<HealthState, React.ReactNode> = {
  healthy: <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />,
  degraded: <AlertTriangle className="h-3.5 w-3.5" aria-hidden />,
  unavailable: <AlertCircle className="h-3.5 w-3.5" aria-hidden />,
};

type HealthBadgeProps = {
  health: HealthState;
  className?: string;
};

export function HealthBadge({ health, className }: HealthBadgeProps) {
  return (
    <Badge variant={HEALTH_STATE_VARIANTS[health]} className={cn("gap-1", className)}>
      {healthIcon[health]}
      {HEALTH_STATE_LABELS[health]}
    </Badge>
  );
}
