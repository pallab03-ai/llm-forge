import { Archive, Beaker, GitBranch, Rocket } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  REGISTRY_STATUS_LABELS,
  REGISTRY_STATUS_VARIANTS,
  type ModelVersionStatus,
} from "@/features/models/schemas";
import { cn } from "@/lib/utils";

const statusIcon: Record<ModelVersionStatus, React.ReactNode> = {
  draft: <Beaker className="h-3.5 w-3.5" aria-hidden />,
  staging: <GitBranch className="h-3.5 w-3.5" aria-hidden />,
  production: <Rocket className="h-3.5 w-3.5" aria-hidden />,
  archived: <Archive className="h-3.5 w-3.5" aria-hidden />,
};

type RegistryStatusBadgeProps = {
  status: ModelVersionStatus;
  className?: string;
};

export function RegistryStatusBadge({ status, className }: RegistryStatusBadgeProps) {
  return (
    <Badge variant={REGISTRY_STATUS_VARIANTS[status]} className={cn("gap-1", className)}>
      {statusIcon[status]}
      {REGISTRY_STATUS_LABELS[status]}
    </Badge>
  );
}
