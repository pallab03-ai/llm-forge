import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MonitoringPage from "@/app/(app)/monitoring/page";
import { AuthProvider } from "@/providers/auth-provider";
import { ApiError } from "@/services/api-client";
import { authStorage } from "@/services/auth-storage";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    refresh: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => "/monitoring",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}));

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
    uploadFile: vi.fn(),
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

const dashboardData = {
  deployment_count: 7,
  active_deployments: 4,
  failed_deployments: 1,
  total_requests: 12345,
  success_rate: 0.987,
  average_latency_ms: 412.7,
};

const baseDeployment = {
  id: "00000000-0000-0000-0000-0000000000d1",
  owner_id: "u-1",
  model_version_id: "00000000-0000-0000-0000-0000000000a1",
  deployment_name: "support-bot",
  status: "active" as const,
  endpoint_name: "support-bot-v1",
  created_at: "2026-02-01T10:00:00Z",
  updated_at: "2026-02-01T10:00:00Z",
};

const healthData = {
  deployment_id: "00000000-0000-0000-0000-0000000000d1",
  status: "active",
  health: "healthy" as const,
  last_checked: "2026-02-01T11:00:00Z",
  message: "All systems normal.",
};

function mockDashboardAndDeployments() {
  apiMock.get.mockImplementation(async (path: string) => {
    if (path === "/monitoring/dashboard") return dashboardData;
    if (path === "/deployments") {
      return { items: [baseDeployment], total: 1, limit: 100, offset: 0 };
    }
    if (path === "/deployments/00000000-0000-0000-0000-0000000000d1/health") return healthData;
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

describe("MonitoringPage", () => {
  it("renders the six dashboard cards with the values returned by the backend", async () => {
    mockDashboardAndDeployments();
    render(
      <TestProviders>
        <MonitoringPage />
      </TestProviders>,
    );

    expect(await screen.findByText("7")).toBeInTheDocument();
    expect(await screen.findByText("Active deployments")).toBeInTheDocument();
    expect(await screen.findByText("12,345")).toBeInTheDocument();
    expect(await screen.findByText("98.7%")).toBeInTheDocument();
    expect(await screen.findByText("413 ms")).toBeInTheDocument();
    expect(screen.getAllByText("4").length).toBeGreaterThan(0);
    expect(screen.getByText("Failed deployments")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("Total requests")).toBeInTheDocument();
    expect(screen.getByText("Success rate")).toBeInTheDocument();
    expect(screen.getByText("Average latency")).toBeInTheDocument();
  });

  it("renders the deployments list with the health verdict from the monitoring endpoint", async () => {
    mockDashboardAndDeployments();
    render(
      <TestProviders>
        <MonitoringPage />
      </TestProviders>,
    );

    expect(await screen.findByText("support-bot")).toBeInTheDocument();
    expect(screen.getByText("Healthy")).toBeInTheDocument();
    const viewLink = await screen.findByRole("link", { name: /view monitoring/i });
    expect(viewLink).toHaveAttribute("href", "/monitoring/00000000-0000-0000-0000-0000000000d1");
  });

  it("shows skeleton placeholders while the dashboard query is loading", () => {
    apiMock.get.mockImplementation(() => new Promise(() => {}));
    render(
      <TestProviders>
        <MonitoringPage />
      </TestProviders>,
    );

    expect(document.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
  });

  it("shows an error state when the dashboard query fails", async () => {
    apiMock.get.mockImplementation(async (path: string) => {
      if (path === "/monitoring/dashboard") {
        throw new ApiError("SERVER_ERROR", "Boom", 500);
      }
      return { items: [], total: 0, limit: 100, offset: 0 };
    });
    render(
      <TestProviders>
        <MonitoringPage />
      </TestProviders>,
    );

    expect(await screen.findByText(/could not load monitoring dashboard/i)).toBeInTheDocument();
  });

  it("shows an empty state when no deployments exist", async () => {
    apiMock.get.mockImplementation(async (path: string) => {
      if (path === "/monitoring/dashboard") return dashboardData;
      if (path === "/deployments") return { items: [], total: 0, limit: 100, offset: 0 };
      throw new Error(`unmocked GET ${path}`);
    });
    render(
      <TestProviders>
        <MonitoringPage />
      </TestProviders>,
    );

    expect(await screen.findByText(/no deployments yet/i)).toBeInTheDocument();
  });

  it("falls back to em-dash placeholders when the dashboard payload is empty", async () => {
    apiMock.get.mockImplementation(async (path: string) => {
      if (path === "/monitoring/dashboard") {
        return {
          deployment_count: 0,
          active_deployments: 0,
          failed_deployments: 0,
          total_requests: 0,
          success_rate: 0,
          average_latency_ms: 0,
        };
      }
      return { items: [], total: 0, limit: 100, offset: 0 };
    });
    render(
      <TestProviders>
        <MonitoringPage />
      </TestProviders>,
    );

    expect(await screen.findByText("0.0%")).toBeInTheDocument();
    expect(screen.getByText("Total deployments")).toBeInTheDocument();
  });
});
