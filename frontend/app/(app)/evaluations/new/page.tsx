"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { EvaluationForm } from "@/components/evaluations/evaluation-form";

export default function NewEvaluationPage() {
  return (
    <div className="space-y-8">
      <Link href="/evaluations" className={buttonVariants({ variant: "ghost", size: "sm" })}>
        <ArrowLeft className="h-4 w-4" />
        All evaluations
      </Link>
      <PageHeader
        title="New evaluation"
        description="Pick a completed training job as the model and a ready dataset as the evaluation target."
      />
      <EvaluationForm />
    </div>
  );
}
