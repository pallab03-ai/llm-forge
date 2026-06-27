import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SidebarContent } from "@/components/layout/sidebar-content";
import { AppProviders } from "@/providers";

function renderWithProviders(node: React.ReactNode) {
  return render(node, { wrapper: AppProviders });
}

describe("Sidebar", () => {
  it("renders every primary navigation item", () => {
    renderWithProviders(<SidebarContent />);

    for (const label of [
      "Dashboard",
      "Datasets",
      "Training",
      "Evaluations",
      "Models",
      "Deployments",
      "Settings",
    ]) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
  });

  it("marks the dashboard link as the current page on /dashboard", () => {
    window.history.pushState({}, "", "/dashboard");
    renderWithProviders(<SidebarContent />);

    const link = screen.getByRole("link", { name: /dashboard/i });
    expect(link).toHaveAttribute("aria-current", "page");
  });
});
