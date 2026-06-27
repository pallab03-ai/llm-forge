import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AppProviders } from "@/providers";
import { useAuth } from "@/hooks/use-auth";

function ReadAuth() {
  const { isAuthenticated } = useAuth();
  return (
    <div>
      <span data-testid="auth">{isAuthenticated ? "yes" : "no"}</span>
    </div>
  );
}

describe("AppProviders", () => {
  it("mounts children inside the provider tree", () => {
    render(
      <AppProviders>
        <div data-testid="child">hello</div>
      </AppProviders>,
    );

    expect(screen.getByTestId("child")).toHaveTextContent("hello");
  });

  it("exposes auth context defaults to logged-out", () => {
    render(
      <AppProviders>
        <ReadAuth />
      </AppProviders>,
    );

    expect(screen.getByTestId("auth")).toHaveTextContent("no");
  });
});
