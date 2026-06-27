import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  DATASET_LABELS,
  FORMAT_LABELS,
  type DatasetDetail,
  type DatasetStatus,
  type DatasetVersion,
} from "@/features/datasets/schemas";

type MetadataCardProps = {
  dataset: DatasetDetail;
  latest: DatasetVersion | null;
};

const statusLabel: Record<DatasetStatus, string> = {
  uploading: "Uploading",
  validating: "Validating",
  ready: "Ready",
  failed: "Failed",
  deleted: "Deleted",
};

const statusVariant: Record<DatasetStatus, "default" | "success" | "warning" | "danger" | "secondary"> = {
  uploading: "warning",
  validating: "warning",
  ready: "success",
  failed: "danger",
  deleted: "secondary",
};

function formatDate(value: string): string {
  return new Date(value).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right">{children}</span>
    </div>
  );
}

export function MetadataCard({ dataset, latest }: MetadataCardProps) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <CardTitle className="text-base">Dataset information</CardTitle>
          <Badge variant={statusVariant[dataset.status]}>{statusLabel[dataset.status]}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-1">
        <Row label="Name">{dataset.name}</Row>
        <Separator />
        <Row label="Description">
          <span className="max-w-xs text-muted-foreground">{dataset.description ?? "—"}</span>
        </Row>
        <Separator />
        <Row label="Type">{DATASET_LABELS[dataset.dataset_type]}</Row>
        <Separator />
        <Row label="Format">{FORMAT_LABELS[dataset.format]}</Row>
        <Separator />
        <Row label="Owner">
          <span className="font-mono text-xs text-muted-foreground">
            {dataset.created_by ? dataset.created_by.slice(0, 8) : "—"}
          </span>
        </Row>
        <Separator />
        <Row label="Created">{formatDate(dataset.created_at)}</Row>
        <Separator />
        <Row label="Latest version">
          {latest ? <span className="font-medium">v{latest.version_number}</span> : "—"}
        </Row>
        <Separator />
        <Row label="Records">
          {latest ? latest.record_count.toLocaleString() : "—"}
        </Row>
        <Separator />
        <Row label="Validation">
          {latest
            ? latest.validation_errors
              ? <Badge variant="warning">Has issues</Badge>
              : <Badge variant="success">Clean</Badge>
            : "—"}
        </Row>
      </CardContent>
    </Card>
  );
}
