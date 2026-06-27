"use client";

import { useEffect, useState } from "react";

interface HealthData {
  status: string;
  version: string;
  environment: string;
}

interface HealthResponse {
  success: boolean;
  data: HealthData;
}

export default function HomePage() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

  useEffect(() => {
    fetch(`${apiBaseUrl}/api/v1/health`)
      .then((res) => res.json())
      .then((data: HealthResponse) => {
        if (data.success) setHealth(data.data);
        else setError("Backend reported an error");
      })
      .catch((err) => setError(err.message));
  }, [apiBaseUrl]);

  return (
    <main className="container mx-auto px-4 py-16">
      <div className="mx-auto max-w-3xl space-y-8">
        <header className="space-y-2">
          <h1 className="text-4xl font-bold tracking-tight">LLM Forge</h1>
          <p className="text-lg text-muted-foreground">
            Production-grade LLMOps platform for fine-tuning, evaluating, and deploying open-source LLMs.
          </p>
        </header>

        <section className="rounded-lg border bg-card p-6 shadow-sm">
          <h2 className="text-xl font-semibold">Backend health</h2>

          <div className="mt-4 rounded-md bg-muted p-4 text-sm">
            {health ? (
              <dl className="grid grid-cols-3 gap-2">
                <dt className="font-medium">Status</dt>
                <dd className="col-span-2 text-green-600">{health.status}</dd>
                <dt className="font-medium">Version</dt>
                <dd className="col-span-2">{health.version}</dd>
                <dt className="font-medium">Environment</dt>
                <dd className="col-span-2">{health.environment}</dd>
              </dl>
            ) : error ? (
              <p className="text-red-600">Backend unreachable: {error}</p>
            ) : (
              <p className="text-muted-foreground">Checking backend…</p>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
