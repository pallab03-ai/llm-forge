"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    if (typeof window !== "undefined") {
      // ponytail: foundation — surface digest in console only, no telemetry yet
      console.error(error);
    }
  }, [error]);

  return (
    <main className="container mx-auto flex min-h-[70vh] items-center justify-center px-4">
      <div className="max-w-md space-y-4 text-center">
        <p className="text-sm font-medium text-muted-foreground">Something went wrong</p>
        <h1 className="text-3xl font-semibold tracking-tight">Application error</h1>
        <p className="text-sm text-muted-foreground">
          An unexpected error occurred. Try again, or come back later.
        </p>
        <div className="flex justify-center gap-2">
          <Button onClick={reset}>Try again</Button>
          <Button variant="outline" onClick={() => (window.location.href = "/")}>
            Go home
          </Button>
        </div>
      </div>
    </main>
  );
}
