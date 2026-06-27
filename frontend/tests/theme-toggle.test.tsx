import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { AppProviders } from "@/providers";
import { useTheme } from "@/providers/theme-provider";

function ReadTheme() {
  const { resolvedTheme, theme } = useTheme();
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <span data-testid="resolved">{resolvedTheme}</span>
    </div>
  );
}

describe("ThemeToggle", () => {
  it("flips between light and dark when clicked", async () => {
    window.localStorage.setItem("llm-forge:theme", "light");
    render(
      <AppProviders>
        <ReadTheme />
        <ThemeToggle />
      </AppProviders>,
    );

    expect(screen.getByTestId("resolved")).toHaveTextContent("light");

    await userEvent.click(screen.getByRole("button", { name: /switch to dark theme/i }));
    expect(screen.getByTestId("resolved")).toHaveTextContent("dark");
    expect(window.localStorage.getItem("llm-forge:theme")).toBe("dark");
  });
});
