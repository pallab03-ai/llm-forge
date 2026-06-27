import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { Badge } from "@/components/ui/badge";
import {
  DATASET_LABELS,
  FORMAT_LABELS,
  type DatasetDetail,
  type DatasetStatus,
} from "@/features/datasets/schemas";

type DatasetHeaderProps = {
  dataset: DatasetDetail;
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

export function DatasetHeader({ dataset }: DatasetHeaderProps) {
  return (
    <div className="space-y-4">
      <Link
        href="/datasets"
        className={buttonVariants({ variant: "ghost", size: "sm" })}
      >
        <ArrowLeft className="h-4 w-4" />
        All datasets
      </Link>
      <PageHeader
        title={dataset.name}
        description={
          dataset.description ??
          `${DATASET_LABELS[dataset.dataset_type]} dataset in ${FORMAT_LABELS[dataset.format]} format.`
        }
        actions={
          <div className="flex items-center gap-2">
            <Badge variant={statusVariant[dataset.status]}>{statusLabel[dataset.status]}</Badge>
            <Link
              href={`/datasets/upload?datasetId=${dataset.id}`}
              className={buttonVariants({ size: "sm" })}
            >
              Upload new version
            </Link>
          </div>
        }
      />
    </div>
  );
}
