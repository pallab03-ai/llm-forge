import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Header } from "@/components/layout/header";
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

afterEach(() => {
  authStorage.clear();
  nav.push.mockReset();
});

describe("Header logout", () => {
  it("clears the session and navigates to /login on click", async () => {
    authStorage.setToken({ accessToken: "tok", tokenType: "bearer", expiresAt: Date.now() + 60_000 });
    authStorage.setUser({ id: "u", email: "ada@example.com", username: "ada", role: "user" });

    const user = userEvent.setup();
    render(
      <AppProviders>
        <Header />
      </AppProviders>,
    );

    const logout = await screen.findByRole("button", { name: /logout/i });
    await user.click(logout);

    await waitFor(() => {
      expect(nav.push).toHaveBeenCalledWith("/login");
    });
    expect(authStorage.getToken()).toBeNull();
    expect(authStorage.getUser()).toBeNull();
  });
});
