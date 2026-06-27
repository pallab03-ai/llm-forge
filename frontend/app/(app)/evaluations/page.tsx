import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";

export default function EvaluationsPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        title="Evaluations"
        description="Run ROUGE, BERTScore, and semantic similarity evaluations."
      />
      <Card>
        <CardHeader>
          <CardTitle>Evaluation runs</CardTitle>
          <CardDescription>Run creation lands in a later phase.</CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Placeholder card for the evaluations workspace.
        </CardContent>
      </Card>
    </div>
  );
}
