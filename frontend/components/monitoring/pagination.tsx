"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type PaginationProps = {
  total: number;
  limit: number;
  offset: number;
  onChange: (next: { limit: number; offset: number }) => void;
  className?: string;
};

export function Pagination({ total, limit, offset, onChange, className }: PaginationProps) {
  const page = Math.floor(offset / limit) + 1;
  const pageCount = Math.max(1, Math.ceil(total / limit));
  const atStart = offset === 0;
  const atEnd = offset + limit >= total;

  const goPrev = () => onChange({ limit, offset: Math.max(0, offset - limit) });
  const goNext = () => onChange({ limit, offset: offset + limit });

  return (
    <div className={cn("flex items-center justify-between gap-3", className)}>
      <p className="text-xs text-muted-foreground" aria-live="polite">
        Page {page} of {pageCount} · {total.toLocaleString()} total
      </p>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={goPrev}
          disabled={atStart}
          aria-label="Previous page"
          className={buttonVariants({ variant: "outline", size: "sm" })}
        >
          <ChevronLeft className="h-4 w-4" />
          Previous
        </button>
        <button
          type="button"
          onClick={goNext}
          disabled={atEnd}
          aria-label="Next page"
          className={buttonVariants({ variant: "outline", size: "sm" })}
        >
          Next
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
