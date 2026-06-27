import { CheckCircle2, Clock, Loader2, XCircle, Ban } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  TRAINING_STATUS_LABELS,
  TRAINING_STATUS_VARIANTS,
  type TrainingStatus,
} from "@/features/training/schemas";
import { cn } from "@/lib/utils";

const statusIcon: Record<TrainingStatus, React.ReactNode> = {
  queued: <Clock className="h-3.5 w-3.5" aria-hidden />,
  running: <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />,
  completed: <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />,
  failed: <XCircle className="h-3.5 w-3.5" aria-hidden />,
  cancelled: <Ban className="h-3.5 w-3.5" aria-hidden />,
};

type TrainingStatusBadgeProps = {
  status: TrainingStatus;
  className?: string;
};

export function TrainingStatusBadge({ status, className }: TrainingStatusBadgeProps) {
  return (
    <Badge variant={TRAINING_STATUS_VARIANTS[status]} className={cn("gap-1", className)}>
      {statusIcon[status]}
      {TRAINING_STATUS_LABELS[status]}
    </Badge>
  );
}
