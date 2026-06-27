import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DeploymentStatusBadge } from "@/components/deployments/deployment-status-badge";

describe("DeploymentStatusBadge", () => {
  it("renders the pending label", () => {
    render(<DeploymentStatusBadge status="pending" />);
    expect(screen.getByText("Pending")).toBeInTheDocument();
  });

  it("renders the deploying label", () => {
    render(<DeploymentStatusBadge status="deploying" />);
    expect(screen.getByText("Deploying")).toBeInTheDocument();
  });

  it("renders the active label", () => {
    render(<DeploymentStatusBadge status="active" />);
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("renders the failed label", () => {
    render(<DeploymentStatusBadge status="failed" />);
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });
});
