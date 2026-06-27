import { GitCompareArrows, ListChecks } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import type { EvaluationStatus } from "@/features/evaluations/schemas";

type EvaluationSectionEmptyProps = {
  kind: "raw-results" | "comparison";
  evaluationStatus: EvaluationStatus;
};

const meta: Record<
  EvaluationSectionEmptyProps["kind"],
  { title: string; description: string; icon: React.ReactNode }
> = {
  "raw-results": {
    title: "Raw results unavailable",
    description:
      "The backend does not return per-record outputs. Aggregated metrics are above.",
    icon: <ListChecks className="h-5 w-5" aria-hidden />,
  },
  comparison: {
    title: "Comparison unavailable",
    description:
      "The backend does not expose a side-by-side evaluation comparison endpoint yet.",
    icon: <GitCompareArrows className="h-5 w-5" aria-hidden />,
  },
};

function titleFor(kind: EvaluationSectionEmptyProps["kind"]): string {
  return kind === "raw-results" ? "Raw results" : "Comparison";
}

function descriptionFor(
  kind: EvaluationSectionEmptyProps["kind"],
  evaluationStatus: EvaluationStatus,
): string {
  if (kind === "raw-results") {
    if (evaluationStatus === "running" || evaluationStatus === "pending") {
      return "Per-record predictions will appear here when the evaluation finishes and the backend starts exposing them.";
    }
    return "The backend did not return any per-record predictions for this evaluation.";
  }
  // comparison
  return "Pick another completed evaluation to compare metrics against. The comparison view will land when the backend supports it.";
}

export function EvaluationSectionEmpty({ kind, evaluationStatus }: EvaluationSectionEmptyProps) {
  const m = meta[kind];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{titleFor(kind)}</CardTitle>
        <CardDescription>{descriptionFor(kind, evaluationStatus)}</CardDescription>
      </CardHeader>
      <CardContent>
        <EmptyState icon={m.icon} title={m.title} description={m.description} />
      </CardContent>
    </Card>
  );
}
