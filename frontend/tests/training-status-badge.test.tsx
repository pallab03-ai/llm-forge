import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TrainingStatusBadge } from "@/components/training/training-status-badge";

describe("TrainingStatusBadge", () => {
  it("renders the queued label", () => {
    render(<TrainingStatusBadge status="queued" />);
    expect(screen.getByText("Queued")).toBeInTheDocument();
  });

  it("renders the running label", () => {
    render(<TrainingStatusBadge status="running" />);
    expect(screen.getByText("Training")).toBeInTheDocument();
  });

  it("renders the completed label", () => {
    render(<TrainingStatusBadge status="completed" />);
    expect(screen.getByText("Completed")).toBeInTheDocument();
  });

  it("renders the failed label", () => {
    render(<TrainingStatusBadge status="failed" />);
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("renders the cancelled label", () => {
    render(<TrainingStatusBadge status="cancelled" />);
    expect(screen.getByText("Cancelled")).toBeInTheDocument();
  });
});
