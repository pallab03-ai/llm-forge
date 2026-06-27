"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { ModelForm } from "@/components/models/model-form";

export default function RegisterModelPage() {
  return (
    <div className="space-y-8">
      <Link href="/models" className={buttonVariants({ variant: "ghost", size: "sm" })}>
        <ArrowLeft className="h-4 w-4" />
        All models
      </Link>
      <PageHeader
        title="Register model"
        description="Create a model container and link its first version to a completed training job and evaluation."
      />
      <ModelForm />
    </div>
  );
}
