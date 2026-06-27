import Link from "next/link";
import * as React from "react";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type QuickActionCardProps = {
  icon: React.ReactNode;
  title: string;
  description: string;
  href: string;
  cta: string;
};

export function QuickActionCard({ icon, title, description, href, cta }: QuickActionCardProps) {
  return (
    <Card className="flex h-full flex-col transition-colors hover:bg-accent/30">
      <CardHeader className="flex-row items-start gap-3 space-y-0">
        <span className="rounded-md bg-muted p-2 text-muted-foreground" aria-hidden>
          {icon}
        </span>
        <div className="space-y-1">
          <CardTitle className="text-base">{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="mt-auto">
        <Link
          href={href}
          className={buttonVariants({ variant: "outline", size: "sm" })}
        >
          {cta}
        </Link>
      </CardContent>
    </Card>
  );
}
