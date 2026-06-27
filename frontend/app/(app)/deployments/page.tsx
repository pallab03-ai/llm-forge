import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";

export default function DeploymentsPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        title="Deployments"
        description="Activate and manage inference deployments."
      />
      <Card>
        <CardHeader>
          <CardTitle>Deployments</CardTitle>
          <CardDescription>Activation and generation land in a later phase.</CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Placeholder card for the deployments workspace.
        </CardContent>
      </Card>
    </div>
  );
}
