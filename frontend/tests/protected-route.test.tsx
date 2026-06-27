import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProtectedRoute } from "@/components/auth/protected-route";
import { AppProviders } from "@/providers";
import { authStorage } from "@/services/auth-storage";

const nav = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
  back: vi.fn(),
  forward: vi.fn(),
  prefetch: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => nav,
  usePathname: () => "/dashboard",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}));

beforeEach(() => {
  authStorage.clear();
  nav.replace.mockReset();
});

afterEach(() => {
  authStorage.clear();
});

describe("ProtectedRoute", () => {
  it("redirects to /login when there is no session", async () => {
    render(
      <AppProviders>
        <ProtectedRoute>
          <div>secret</div>
        </ProtectedRoute>
      </AppProviders>,
    );

    await waitFor(() => {
      expect(nav.replace).toHaveBeenCalledWith("/login");
    });
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
  });

  it("renders children when authenticated", async () => {
    authStorage.setToken({ accessToken: "tok", tokenType: "bearer", expiresAt: Date.now() + 60_000 });
    authStorage.setUser({ id: "u", email: "u@example.com", username: "u", role: "user" });

    render(
      <AppProviders>
        <ProtectedRoute>
          <div>secret</div>
        </ProtectedRoute>
      </AppProviders>,
    );

    expect(await screen.findByText("secret")).toBeInTheDocument();
    expect(nav.replace).not.toHaveBeenCalled();
  });
});
