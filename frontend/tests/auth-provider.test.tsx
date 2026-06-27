import { act, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "@/providers/auth-provider";
import { useAuth } from "@/hooks/use-auth";
import { ApiError } from "@/services/api-client";
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
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}));

const apiMock = vi.hoisted(() => ({
  post: vi.fn(),
  get: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));

vi.mock("@/services/api-client", async () => {
  class ApiErrorMock extends Error {
    code: string;
    status: number;
    constructor(code: string, message: string, status: number) {
      super(message);
      this.code = code;
      this.status = status;
    }
  }
  return {
    ApiError: ApiErrorMock,
    apiClient: apiMock,
    apiRequest: vi.fn(),
    setUnauthorizedHandler: vi.fn(),
  };
});

let latest: ReturnType<typeof useAuth> | null = null;

function Capture() {
  const api = useAuth();
  latest = api;
  return null;
}

function renderProvider() {
  render(
    <AuthProvider>
      <Capture />
    </AuthProvider>,
  );
}

beforeEach(() => {
  latest = null;
  authStorage.clear();
  apiMock.post.mockReset();
  apiMock.get.mockReset();
});

afterEach(() => {
  authStorage.clear();
});

async function waitForHydration() {
  await waitFor(() => {
    expect(latest).not.toBeNull();
    expect(latest!.isHydrated).toBe(true);
  });
}

describe("AuthProvider", () => {
  it("logs in and persists the session on success", async () => {
    apiMock.post.mockResolvedValueOnce({
      access_token: "tok-1",
      token_type: "bearer",
      expires_in: 3600,
      user: { id: "u-1", email: "ada@example.com", username: "ada", role: "user" },
    });

    renderProvider();
    await waitForHydration();

    await act(async () => {
      await latest!.login("ada@example.com", "secret123");
    });

    await waitFor(() => expect(latest!.isAuthenticated).toBe(true));
    expect(latest!.user?.email).toBe("ada@example.com");
    expect(authStorage.getToken()?.accessToken).toBe("tok-1");
    expect(authStorage.getUser()?.username).toBe("ada");
  });

  it("does not persist anything when login fails", async () => {
    apiMock.post.mockRejectedValueOnce(new ApiError("INVALID_CREDENTIALS", "Invalid", 401));

    renderProvider();
    await waitForHydration();

    await expect(latest!.login("ada@example.com", "wrong")).rejects.toBeInstanceOf(ApiError);

    expect(latest!.isAuthenticated).toBe(false);
    expect(authStorage.getToken()).toBeNull();
  });

  it("logs out and clears the stored session", async () => {
    apiMock.post.mockResolvedValueOnce({
      access_token: "tok-1",
      token_type: "bearer",
      expires_in: 3600,
      user: { id: "u-1", email: "ada@example.com", username: "ada", role: "user" },
    });

    renderProvider();
    await waitForHydration();

    await act(async () => {
      await latest!.login("ada@example.com", "secret123");
    });
    await waitFor(() => expect(latest!.isAuthenticated).toBe(true));

    act(() => latest!.logout());

    await waitFor(() => expect(latest!.isAuthenticated).toBe(false));
    expect(authStorage.getToken()).toBeNull();
    expect(authStorage.getUser()).toBeNull();
  });

  it("rejects login with a network error", async () => {
    apiMock.post.mockRejectedValueOnce(new TypeError("NetworkError"));

    renderProvider();
    await waitForHydration();

    await expect(latest!.login("ada@example.com", "secret123")).rejects.toThrow(TypeError);
    expect(latest!.isAuthenticated).toBe(false);
  });

  it("refreshes the user from /me when a stored token is present", async () => {
    authStorage.setToken({ accessToken: "tok-stored", tokenType: "bearer", expiresAt: Date.now() + 60_000 });
    authStorage.setUser({ id: "old", email: "old@example.com", username: "old", role: "user" });

    apiMock.get.mockResolvedValueOnce({
      id: "u-fresh",
      email: "fresh@example.com",
      username: "fresh",
      role: "admin",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });

    renderProvider();
    await waitForHydration();

    await waitFor(() => expect(latest!.user?.username).toBe("fresh"));
    expect(latest!.user?.role).toBe("admin");
    expect(authStorage.getUser()?.username).toBe("fresh");
  });

  it("clears the stored session when /me returns 401", async () => {
    authStorage.setToken({ accessToken: "expired", tokenType: "bearer", expiresAt: Date.now() - 1000 });
    authStorage.setUser({ id: "u", email: "u@example.com", username: "u", role: "user" });

    apiMock.get.mockRejectedValueOnce(new ApiError("INVALID_TOKEN", "Expired", 401));

    renderProvider();
    await waitForHydration();

    await waitFor(() => expect(latest!.isAuthenticated).toBe(false));
    expect(authStorage.getToken()).toBeNull();
    expect(authStorage.getUser()).toBeNull();
  });
});
