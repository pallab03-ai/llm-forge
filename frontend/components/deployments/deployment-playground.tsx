"use client";

import { useState } from "react";
import { Copy, Send } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import {
  MAX_PROMPT_LENGTH,
  canGenerate,
  type Deployment,
} from "@/features/deployments/schemas";
import { useGenerate } from "@/features/deployments/queries";
import { ApiError } from "@/services/api-client";

type DeploymentPlaygroundProps = {
  deployment: Deployment;
};

export function DeploymentPlayground({ deployment }: DeploymentPlaygroundProps) {
  const [prompt, setPrompt] = useState("");
  const generate = useGenerate(deployment.id);

  const charCount = prompt.length;
  const overLimit = charCount > MAX_PROMPT_LENGTH;
  const empty = prompt.trim().length === 0;
  const disabled = !canGenerate(deployment.status) || empty || overLimit;

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (disabled) return;
    try {
      await generate.mutateAsync(prompt);
    } catch {
      // Error is rendered inline via generate.isError below.
    }
  };

  const onCopy = async () => {
    if (!generate.data) return;
    try {
      await navigator.clipboard.writeText(generate.data.response);
      toast.success("Copied response to clipboard.");
    } catch {
      toast.error("Could not copy to clipboard.");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Inference playground</CardTitle>
        <CardDescription>
          Run a prompt against the deployed model. Requires an active deployment.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!canGenerate(deployment.status) ? (
          <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground" role="status">
            The deployment is {deployment.status}. Activate it to run inference.
          </p>
        ) : (
          <form className="space-y-3" onSubmit={onSubmit}>
            <div className="space-y-2">
              <label htmlFor="prompt" className="text-sm font-medium">
                Prompt
              </label>
              <textarea
                id="prompt"
                rows={5}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="Type a prompt for the model…"
                className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={generate.isPending}
                aria-invalid={overLimit}
                aria-describedby="prompt-counter"
              />
              <div
                id="prompt-counter"
                className={
                  overLimit
                    ? "flex items-center justify-between text-xs text-destructive"
                    : "flex items-center justify-between text-xs text-muted-foreground"
                }
              >
                <span>
                  {charCount} / {MAX_PROMPT_LENGTH} characters
                </span>
                {overLimit ? <span>Prompt exceeds the 4096-character limit.</span> : null}
              </div>
            </div>

            <div className="flex justify-end">
              <Button type="submit" disabled={disabled || generate.isPending}>
                {generate.isPending ? <Spinner size="sm" label="Generating" /> : <Send className="h-4 w-4" />}
                Generate
              </Button>
            </div>
          </form>
        )}

        {generate.isError ? (
          <div role="alert" className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
            {generate.error instanceof ApiError
              ? generate.error.message
              : "Network error. Check your connection and try again."}
          </div>
        ) : null}

        {generate.data ? (
          <div className="space-y-2 rounded-md border bg-muted/30 p-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Generated response
              </span>
              <Button type="button" variant="ghost" size="sm" onClick={onCopy}>
                <Copy className="h-3.5 w-3.5" />
                Copy
              </Button>
            </div>
            <pre className="whitespace-pre-wrap break-words text-sm">{generate.data.response}</pre>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
