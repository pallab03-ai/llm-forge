import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HealthBadge } from "@/components/monitoring/health-badge";

describe("HealthBadge", () => {
  it("renders Healthy for the healthy state", () => {
    render(<HealthBadge health="healthy" />);
    expect(screen.getByText("Healthy")).toBeInTheDocument();
  });

  it("renders Degraded for the degraded state", () => {
    render(<HealthBadge health="degraded" />);
    expect(screen.getByText("Degraded")).toBeInTheDocument();
  });

  it("renders Unavailable for the unavailable state", () => {
    render(<HealthBadge health="unavailable" />);
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
  });
});
