"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { DeploymentForm } from "@/components/deployments/deployment-form";

export default function NewDeploymentPage() {
  return (
    <div className="space-y-8">
      <Link href="/deployments" className={buttonVariants({ variant: "ghost", size: "sm" })}>
        <ArrowLeft className="h-4 w-4" />
        All deployments
      </Link>
      <PageHeader
        title="New deployment"
        description="Pick a non-archived model version and create a deployment. The adapter is loaded when you activate it."
      />
      <DeploymentForm />
    </div>
  );
}
