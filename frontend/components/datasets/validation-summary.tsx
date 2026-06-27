import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { CheckCircle2, AlertTriangle, XCircle } from "lucide-react";
import { type ValidationEntry } from "@/features/datasets/schemas";

type ValidationSummaryProps = {
  rawJson: string | null;
};

const severityMeta: Record<ValidationEntry["severity"], { variant: "success" | "warning" | "danger"; label: string; icon: React.ReactNode }> = {
  pass: { variant: "success", label: "Pass", icon: <CheckCircle2 className="h-3.5 w-3.5" aria-hidden /> },
  warning: { variant: "warning", label: "Warning", icon: <AlertTriangle className="h-3.5 w-3.5" aria-hidden /> },
  fail: { variant: "danger", label: "Fail", icon: <XCircle className="h-3.5 w-3.5" aria-hidden /> },
};

function parseEntries(rawJson: string | null): ValidationEntry[] | "raw" | null {
  if (!rawJson) return null;
  try {
    const parsed = JSON.parse(rawJson);
    if (Array.isArray(parsed)) return parsed as ValidationEntry[];
    return "raw";
  } catch {
    return "raw";
  }
}

export function ValidationSummary({ rawJson }: ValidationSummaryProps) {
  const parsed = parseEntries(rawJson);

  if (parsed === null) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Validation</CardTitle>
          <CardDescription>Backend did not report any validation issues for this version.</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  if (parsed === "raw") {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Validation</CardTitle>
          <CardDescription>Raw validation payload from the backend.</CardDescription>
        </CardHeader>
        <CardContent>
          <pre className="overflow-x-auto rounded-md bg-muted/40 p-3 text-xs">{rawJson}</pre>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Validation</CardTitle>
        <CardDescription>
          {parsed.length === 0
            ? "No validation issues recorded."
            : `${parsed.length} validation ${parsed.length === 1 ? "entry" : "entries"} returned by the server.`}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {parsed.length === 0 ? null : (
          <ul className="space-y-2">
            {parsed.map((entry, i) => {
              const meta = severityMeta[entry.severity] ?? severityMeta.warning;
              return (
                <li key={`${entry.code}-${i}`} className="flex items-start justify-between gap-3 rounded-md border bg-card/40 p-3">
                  <div className="min-w-0 space-y-0.5">
                    <p className="text-sm font-medium">{entry.message}</p>
                    <p className="text-xs text-muted-foreground">{entry.code}</p>
                  </div>
                  <Badge variant={meta.variant} className="flex-shrink-0 gap-1">
                    {meta.icon}
                    {meta.label}
                  </Badge>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
