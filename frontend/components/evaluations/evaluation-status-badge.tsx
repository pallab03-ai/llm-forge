import { CheckCircle2, Clock, Loader2, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  EVALUATION_STATUS_LABELS,
  EVALUATION_STATUS_VARIANTS,
  type EvaluationStatus,
} from "@/features/evaluations/schemas";
import { cn } from "@/lib/utils";

const statusIcon: Record<EvaluationStatus, React.ReactNode> = {
  pending: <Clock className="h-3.5 w-3.5" aria-hidden />,
  running: <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />,
  completed: <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />,
  failed: <XCircle className="h-3.5 w-3.5" aria-hidden />,
};

type EvaluationStatusBadgeProps = {
  status: EvaluationStatus;
  className?: string;
};

export function EvaluationStatusBadge({ status, className }: EvaluationStatusBadgeProps) {
  return (
    <Badge variant={EVALUATION_STATUS_VARIANTS[status]} className={cn("gap-1", className)}>
      {statusIcon[status]}
      {EVALUATION_STATUS_LABELS[status]}
    </Badge>
  );
}
