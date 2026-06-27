import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";

export default function ModelsPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        title="Models"
        description="Model registry, versions, and promotion workflow."
      />
      <Card>
        <CardHeader>
          <CardTitle>Model registry</CardTitle>
          <CardDescription>Versioning and promotion land in a later phase.</CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Placeholder card for the model registry workspace.
        </CardContent>
      </Card>
    </div>
  );
}
