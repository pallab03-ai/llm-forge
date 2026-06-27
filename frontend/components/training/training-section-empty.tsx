import { Activity, FileText, Package } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";

type TrainingSectionEmptyProps = {
  kind: "metrics" | "logs" | "artifacts";
  jobStatus: "queued" | "running" | "completed" | "failed" | "cancelled";
  artifactPath?: string | null;
};

const meta: Record<
  TrainingSectionEmptyProps["kind"],
  { title: string; description: string; icon: React.ReactNode }
> = {
  metrics: {
    title: "Metrics unavailable",
    description: "The backend does not expose a metrics endpoint for this job yet.",
    icon: <Activity className="h-5 w-5" aria-hidden />,
  },
  logs: {
    title: "Logs unavailable",
    description: "The backend does not expose a log streaming endpoint for this job yet.",
    icon: <FileText className="h-5 w-5" aria-hidden />,
  },
  artifacts: {
    title: "Artifacts unavailable",
    description:
      "The backend does not expose a download endpoint for this job yet. Adapters and reports will appear here when it does.",
    icon: <Package className="h-5 w-5" aria-hidden />,
  },
};

export function TrainingSectionEmpty({ kind, jobStatus, artifactPath }: TrainingSectionEmptyProps) {
  const m = meta[kind];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{titleFor(kind)}</CardTitle>
        <CardDescription>{descriptionFor(kind, jobStatus, artifactPath)}</CardDescription>
      </CardHeader>
      <CardContent>
        <EmptyState
          icon={m.icon}
          title={m.title}
          description={m.description}
        />
      </CardContent>
    </Card>
  );
}

function titleFor(kind: TrainingSectionEmptyProps["kind"]): string {
  if (kind === "metrics") return "Metrics";
  if (kind === "logs") return "Logs";
  return "Artifacts";
}

function descriptionFor(
  kind: TrainingSectionEmptyProps["kind"],
  jobStatus: TrainingSectionEmptyProps["jobStatus"],
  artifactPath?: string | null,
): string {
  if (kind === "artifacts" && jobStatus === "completed" && artifactPath) {
    return `Artifact path on the server: ${artifactPath}`;
  }
  if (kind === "artifacts" && jobStatus === "completed") {
    return "The job completed but the backend did not return an artifact path.";
  }
  if (kind === "logs" && (jobStatus === "running" || jobStatus === "queued")) {
    return "The job is running, but the backend does not expose logs yet.";
  }
  if (kind === "metrics" && (jobStatus === "running" || jobStatus === "queued")) {
    return "The job is running, but the backend does not expose metrics yet.";
  }
  return "No data to display.";
}
