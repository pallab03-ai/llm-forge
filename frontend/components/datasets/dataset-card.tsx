import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { FORMAT_LABELS, DATASET_LABELS, type DatasetItem } from "@/features/datasets/schemas";
import { cn } from "@/lib/utils";

type DatasetCardProps = {
  dataset: DatasetItem;
  href?: string;
  sample?: boolean;
  className?: string;
};

export function DatasetCard({ dataset, href, sample = false, className }: DatasetCardProps) {
  return (
    <Card className={cn("relative h-full", className)}>
      {sample ? (
        <span className="absolute right-3 top-3">
          <Badge variant="secondary">Sample</Badge>
        </span>
      ) : null}
      <CardHeader>
        <CardTitle className="truncate text-base">{dataset.name}</CardTitle>
        <CardDescription className="line-clamp-2">
          {dataset.description ?? "No description provided."}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex items-end justify-between gap-3">
        <div className="space-y-1 text-xs text-muted-foreground">
          <p>
            <span className="font-medium text-foreground">{DATASET_LABELS[dataset.dataset_type]}</span>
            <span aria-hidden> · </span>
            <span>{FORMAT_LABELS[dataset.format]}</span>
          </p>
          <p>
            <span className="font-medium text-foreground">Records:</span> —
          </p>
        </div>
        {href ? (
          <Link href={href} className={buttonVariants({ variant: "outline", size: "sm" })}>
            Open
          </Link>
        ) : null}
      </CardContent>
    </Card>
  );
}
