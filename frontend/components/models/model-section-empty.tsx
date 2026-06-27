import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Box, History, Rocket } from "lucide-react";

type ModelSectionEmptyProps = {
  kind: "no-versions" | "no-evaluation" | "no-promotion";
};

const meta: Record<
  ModelSectionEmptyProps["kind"],
  { title: string; description: string; icon: React.ReactNode }
> = {
  "no-versions": {
    title: "No versions yet",
    description: "Register a version by linking a completed training job and the evaluation that validated it.",
    icon: <Box className="h-5 w-5" aria-hidden />,
  },
  "no-evaluation": {
    title: "No evaluation snapshot",
    description: "The metrics_snapshot is empty for this version. The backend did not return evaluation metrics at registration time.",
    icon: <History className="h-5 w-5" aria-hidden />,
  },
  "no-promotion": {
    title: "Promotion workflow unavailable",
    description: "The backend exposes promote and archive for individual versions. Rollback is not implemented yet.",
    icon: <Rocket className="h-5 w-5" aria-hidden />,
  },
};

function titleFor(kind: ModelSectionEmptyProps["kind"]): string {
  if (kind === "no-versions") return "Version history";
  if (kind === "no-evaluation") return "Evaluation summary";
  return "Registry status";
}

export function ModelSectionEmpty({ kind }: ModelSectionEmptyProps) {
  const m = meta[kind];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{titleFor(kind)}</CardTitle>
        <CardDescription>{m.description}</CardDescription>
      </CardHeader>
      <CardContent>
        <EmptyState icon={m.icon} title={m.title} description={m.description} />
      </CardContent>
    </Card>
  );
}
