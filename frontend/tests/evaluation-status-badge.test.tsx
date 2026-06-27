import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EvaluationStatusBadge } from "@/components/evaluations/evaluation-status-badge";

describe("EvaluationStatusBadge", () => {
  it("renders the pending label", () => {
    render(<EvaluationStatusBadge status="pending" />);
    expect(screen.getByText("Queued")).toBeInTheDocument();
  });

  it("renders the running label", () => {
    render(<EvaluationStatusBadge status="running" />);
    expect(screen.getByText("Running")).toBeInTheDocument();
  });

  it("renders the completed label", () => {
    render(<EvaluationStatusBadge status="completed" />);
    expect(screen.getByText("Completed")).toBeInTheDocument();
  });

  it("renders the failed label", () => {
    render(<EvaluationStatusBadge status="failed" />);
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });
});
