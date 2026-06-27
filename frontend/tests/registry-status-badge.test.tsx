import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RegistryStatusBadge } from "@/components/models/registry-status-badge";

describe("RegistryStatusBadge", () => {
  it("renders the draft label", () => {
    render(<RegistryStatusBadge status="draft" />);
    expect(screen.getByText("Draft")).toBeInTheDocument();
  });

  it("renders the staging label", () => {
    render(<RegistryStatusBadge status="staging" />);
    expect(screen.getByText("Staging")).toBeInTheDocument();
  });

  it("renders the production label", () => {
    render(<RegistryStatusBadge status="production" />);
    expect(screen.getByText("Production")).toBeInTheDocument();
  });

  it("renders the archived label", () => {
    render(<RegistryStatusBadge status="archived" />);
    expect(screen.getByText("Archived")).toBeInTheDocument();
  });
});
