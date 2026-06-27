import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function HomePage() {
  return (
    <main className="container mx-auto px-4 py-16">
      <div className="mx-auto flex max-w-3xl flex-col gap-8">
        <header className="space-y-2">
          <h1 className="text-4xl font-bold tracking-tight">LLM Forge</h1>
          <p className="text-lg text-muted-foreground">
            Production-grade LLMOps platform for fine-tuning, evaluating, and deploying open-source LLMs.
          </p>
        </header>

        <Card>
          <CardHeader>
            <CardTitle>Welcome</CardTitle>
            <CardDescription>
              Sign in to manage datasets, training jobs, evaluations, and deployments.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            <Link href="/login" className={buttonVariants()}>
              Sign in
            </Link>
            <Link href="/register" className={buttonVariants({ variant: "outline" })}>
              Create account
            </Link>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
