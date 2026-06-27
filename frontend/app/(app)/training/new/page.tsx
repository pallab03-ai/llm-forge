"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { TrainingForm } from "@/components/training/training-form";

export default function NewTrainingJobPage() {
  return (
    <div className="space-y-8">
      <Link href="/training" className={buttonVariants({ variant: "ghost", size: "sm" })}>
        <ArrowLeft className="h-4 w-4" />
        All training jobs
      </Link>
      <PageHeader
        title="New training job"
        description="Pick a base model, a ready dataset, a training method, and the four hyperparameters the backend accepts."
      />
      <TrainingForm />
    </div>
  );
}
