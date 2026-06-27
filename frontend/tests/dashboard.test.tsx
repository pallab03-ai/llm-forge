import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import DashboardPage from "@/app/(app)/dashboard/page";
import { AuthProvider } from "@/providers/auth-provider";
import { ApiError } from "@/services/api-client";
import { authStorage } from "@/services/auth-storage";

const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
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

function TestProviders({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  return (
    <QueryClientProvider client={client}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  );
}

const mePayload = {
  id: "u-1",
  email: "ada@example.com",
  username: "ada",
  role: "user",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const healthPayload = { status: "healthy", version: "1.0.0", environment: "development" };

const counts: Record<string, number> = {
  "/datasets": 12,
  "/training-jobs": 3,
  "/evaluations": 7,
  "/models": 5,
  "/deployments": 2,
};

function happyImplementation() {
  return apiMock.get.mockImplementation(async (path: string) => {
    if (path === "/me") return mePayload;
    if (path === "/health") return healthPayload;
    if (path in counts) {
      return { items: [], total: counts[path], limit: 1, offset: 0 };
    }
    throw new Error(`unmocked GET ${path}`);
  });
}

beforeEach(() => {
  authStorage.clear();
  authStorage.setToken({ accessToken: "tok", tokenType: "bearer", expiresAt: Date.now() + 60_000 });
  authStorage.setUser({ id: "u-1", email: "ada@example.com", username: "ada", role: "user" });
  apiMock.get.mockReset();
  apiMock.post.mockReset();
});

afterEach(() => {
  authStorage.clear();
});

describe("DashboardPage", () => {
  it("renders the welcome section with the logged-in user and role", async () => {
    happyImplementation();
    render(
      <TestProviders>
        <DashboardPage />
      </TestProviders>,
    );

    expect(await screen.findByRole("heading", { name: /ada/i })).toBeInTheDocument();
    expect(screen.getByText(/ready to train your next model/i)).toBeInTheDocument();
    expect(screen.getByText(/member/i)).toBeInTheDocument();
  });

  it("shows skeleton placeholders while queries are loading", () => {
    apiMock.get.mockImplementation(() => new Promise(() => {}));
    render(
      <TestProviders>
        <DashboardPage />
      </TestProviders>,
    );

    // The stat-card skeleton uses the Skeleton primitive (animate-pulse).
    const skeletons = document.querySelectorAll(".animate-pulse");
    expect(skeletons.length).toBeGreaterThan(0);
    // Counts are not rendered yet.
    expect(screen.queryByText("12")).not.toBeInTheDocument();
  });

  it("renders resolved counts in the stat cards", async () => {
    happyImplementation();
    render(
      <TestProviders>
        <DashboardPage />
      </TestProviders>,
    );

    expect(await screen.findByText("12")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("renders an em-dash placeholder when a count query fails", async () => {
    apiMock.get.mockImplementation(async (path: string) => {
      if (path === "/me") return mePayload;
      if (path === "/health") return healthPayload;
      if (path === "/datasets") {
        throw new ApiError("SERVER_ERROR", "Boom", 500);
      }
      if (path in counts) {
        return { items: [], total: counts[path], limit: 1, offset: 0 };
      }
      throw new Error(`unmocked GET ${path}`);
    });

    render(
      <TestProviders>
        <DashboardPage />
      </TestProviders>,
    );

    // The failed card shows "—" while the rest resolve to numbers.
    await waitFor(() => {
      expect(screen.getByText("3")).toBeInTheDocument();
    });
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(1);
  });

  it("links quick actions to the correct routes", async () => {
    happyImplementation();
    render(
      <TestProviders>
        <DashboardPage />
      </TestProviders>,
    );

    expect(await screen.findByRole("link", { name: /^upload$/i })).toHaveAttribute("href", "/datasets");
    expect(screen.getByRole("link", { name: /^create$/i })).toHaveAttribute("href", "/training");
    expect(screen.getByRole("link", { name: /^run$/i })).toHaveAttribute("href", "/evaluations");
    expect(screen.getByRole("link", { name: /^register$/i })).toHaveAttribute("href", "/models");
    expect(screen.getByRole("link", { name: /^deploy$/i })).toHaveAttribute("href", "/deployments");
  });

  it("shows the activity timeline empty state", async () => {
    happyImplementation();
    render(
      <TestProviders>
        <DashboardPage />
      </TestProviders>,
    );

    expect(await screen.findByText(/no recent activity/i)).toBeInTheDocument();
  });

  it("renders the system status section with API and unknown services", async () => {
    happyImplementation();
    render(
      <TestProviders>
        <DashboardPage />
      </TestProviders>,
    );

    expect(await screen.findByText("API")).toBeInTheDocument();
    expect(screen.getByText("Authentication")).toBeInTheDocument();
    expect(screen.getByText("Deployment service")).toBeInTheDocument();
    expect(screen.getByText("Database")).toBeInTheDocument();
    expect(screen.getByText("GPU")).toBeInTheDocument();
    // API is operational because the mock returns status: "healthy".
    const operational = screen.getAllByText("Operational");
    expect(operational.length).toBeGreaterThanOrEqual(1);
    // GPU has no backend endpoint → unknown.
    const unknown = screen.getAllByText("Unknown");
    expect(unknown.length).toBeGreaterThanOrEqual(1);
  });
});
