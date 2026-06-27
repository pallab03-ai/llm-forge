import { AlertCircle, CheckCircle2, CircleDashed, Rocket } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  DEPLOYMENT_STATUS_LABELS,
  DEPLOYMENT_STATUS_VARIANTS,
  type DeploymentStatus,
} from "@/features/deployments/schemas";
import { cn } from "@/lib/utils";

const statusIcon: Record<DeploymentStatus, React.ReactNode> = {
  pending: <CircleDashed className="h-3.5 w-3.5" aria-hidden />,
  deploying: <Rocket className="h-3.5 w-3.5" aria-hidden />,
  active: <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />,
  failed: <AlertCircle className="h-3.5 w-3.5" aria-hidden />,
};

type DeploymentStatusBadgeProps = {
  status: DeploymentStatus;
  className?: string;
};

export function DeploymentStatusBadge({ status, className }: DeploymentStatusBadgeProps) {
  return (
    <Badge variant={DEPLOYMENT_STATUS_VARIANTS[status]} className={cn("gap-1", className)}>
      {statusIcon[status]}
      {DEPLOYMENT_STATUS_LABELS[status]}
    </Badge>
  );
}
