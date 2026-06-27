import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import type { TrainingJob } from "@/features/training/schemas";

type TrainingConfigCardProps = {
  job: TrainingJob;
};

const order: Array<{ key: string; label: string }> = [
  { key: "epochs", label: "Epochs" },
  { key: "batch_size", label: "Batch size" },
  { key: "learning_rate", label: "Learning rate" },
  { key: "max_seq_length", label: "Max sequence length" },
];

function formatValue(key: string, value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (key === "learning_rate") return String(value);
  return typeof value === "number" ? value.toLocaleString() : String(value);
}

export function TrainingConfigCard({ job }: TrainingConfigCardProps) {
  const config = job.configuration ?? {};

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Training configuration</CardTitle>
        <CardDescription>Hyperparameters stored with the job.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-1">
        {order.map(({ key, label }, i) => (
          <div key={key}>
            <div className="flex items-start justify-between gap-3 py-2 text-sm">
              <span className="text-muted-foreground">{label}</span>
              <span className="text-right font-medium tabular-nums">
                {formatValue(key, config[key])}
              </span>
            </div>
            {i < order.length - 1 ? <Separator /> : null}
          </div>
        ))}
        {Object.keys(config).filter((k) => !order.find((o) => o.key === k)).length > 0 ? (
          <>
            <Separator />
            <div className="pt-2">
              <p className="text-xs text-muted-foreground">Additional parameters</p>
              <pre className="mt-1 overflow-x-auto rounded-md bg-muted/40 p-2 text-xs">
                {JSON.stringify(
                  Object.fromEntries(
                    Object.entries(config).filter(([k]) => !order.find((o) => o.key === k)),
                  ),
                  null,
                  2,
                )}
              </pre>
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
