import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Suspense } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import DeploymentMonitoringPage from "@/app/(app)/monitoring/[deploymentId]/page";
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
  usePathname: () => "/monitoring/00000000-0000-0000-0000-0000000000d1",
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
      <AuthProvider>
        <Suspense fallback={<div>Loading</div>}>{children}</Suspense>
      </AuthProvider>
    </QueryClientProvider>
  );
}

const deploymentId = "00000000-0000-0000-0000-0000000000d1";

const baseDeployment = {
  id: deploymentId,
  owner_id: "u-1",
  model_version_id: "00000000-0000-0000-0000-0000000000a1",
  deployment_name: "support-bot",
  status: "active" as const,
  endpoint_name: "support-bot-v1",
  created_at: "2026-02-01T10:00:00Z",
  updated_at: "2026-02-01T10:00:00Z",
};

type HealthShape = {
  deployment_id: string;
  status: string;
  health: "healthy" | "degraded" | "unavailable";
  last_checked: string;
  message: string;
};

const healthyHealth: HealthShape = {
  deployment_id: deploymentId,
  status: "active",
  health: "healthy",
  last_checked: "2026-02-01T11:00:00Z",
  message: "All systems normal.",
};

const degradedHealth: HealthShape = {
  ...healthyHealth,
  health: "degraded",
  message: "High failure rate (60% of last 10 requests).",
};

const metricsData = {
  request_count: 100,
  success_count: 90,
  failure_count: 10,
  average_latency_ms: 250.5,
  min_latency_ms: 80,
  max_latency_ms: 1500,
};

const requestsPage1 = {
  items: [
    { id: "r1", timestamp: "2026-02-01T10:00:10Z", latency_ms: 230, status: "success" as const, prompt_length: 12, response_length: 34 },
    { id: "r2", timestamp: "2026-02-01T10:00:05Z", latency_ms: 410, status: "failure" as const, prompt_length: 20, response_length: null },
  ],
  total: 60,
  limit: 50,
  offset: 0,
};

const requestsPage2 = {
  items: [
    { id: "r3", timestamp: "2026-02-01T09:00:00Z", latency_ms: 180, status: "success" as const, prompt_length: 8, response_length: 16 },
  ],
  total: 60,
  limit: 50,
  offset: 50,
};

const errorsPage1 = {
  items: [
    { timestamp: "2026-02-01T10:00:05Z", error_type: "INFERENCE_ERROR", message: "Adapter failed to load.", status_code: 409 },
  ],
  total: 1,
  limit: 50,
  offset: 0,
};

function mockAll(deployment: typeof baseDeployment = baseDeployment, health: HealthShape = healthyHealth) {
  apiMock.get.mockImplementation(async (path: string, params?: { offset?: number }) => {
    if (path === `/deployments/${deploymentId}`) return deployment;
    if (path === `/deployments/${deploymentId}/health`) return health;
    if (path === `/deployments/${deploymentId}/metrics`) return metricsData;
    if (path === `/deployments/${deploymentId}/requests`) {
      const offset = params?.offset ?? 0;
      return offset === 0 ? requestsPage1 : requestsPage2;
    }
    if (path === `/deployments/${deploymentId}/errors`) return errorsPage1;
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

describe("DeploymentMonitoringPage", () => {
  it("renders the deployment header, info, health, metrics, requests, and errors", async () => {
    mockAll();
    render(
      <TestProviders>
        <DeploymentMonitoringPage params={Promise.resolve({ deploymentId })} />
      </TestProviders>,
    );

    expect(await screen.findByRole("heading", { level: 1, name: "support-bot" })).toBeInTheDocument();
    expect(screen.getByText(/deployment information/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Health" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: /metrics/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: /recent requests/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: /recent errors/i })).toBeInTheDocument();
    expect(await screen.findByText("Healthy")).toBeInTheDocument();
    expect(await screen.findByText("All systems normal.")).toBeInTheDocument();
    expect(await screen.findByText("100")).toBeInTheDocument();
    expect(await screen.findByText("90")).toBeInTheDocument();
    expect(await screen.findByText("251 ms")).toBeInTheDocument();
  });

  it("renders the degraded health verdict with its message", async () => {
    mockAll(baseDeployment, degradedHealth);
    render(
      <TestProviders>
        <DeploymentMonitoringPage params={Promise.resolve({ deploymentId })} />
      </TestProviders>,
    );

    expect(await screen.findByText("Degraded")).toBeInTheDocument();
    expect(screen.getByText(/high failure rate/i)).toBeInTheDocument();
  });

  it("renders the not-found empty state on a 404 from the deployment endpoint", async () => {
    apiMock.get.mockImplementation(async () => {
      throw new ApiError("DEPLOYMENT_NOT_FOUND", "Not found", 404);
    });
    render(
      <TestProviders>
        <DeploymentMonitoringPage params={Promise.resolve({ deploymentId })} />
      </TestProviders>,
    );

    expect(await screen.findByText(/deployment not found/i)).toBeInTheDocument();
  });

  it("renders skeleton placeholders while loading", async () => {
    apiMock.get.mockImplementation(() => new Promise(() => {}));
    render(
      <TestProviders>
        <DeploymentMonitoringPage params={Promise.resolve({ deploymentId })} />
      </TestProviders>,
    );

    await waitFor(() => {
      expect(document.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
    });
  });

  it("paginates the recent requests list when Next is clicked", async () => {
    mockAll();
    const user = userEvent.setup();
    render(
      <TestProviders>
        <DeploymentMonitoringPage params={Promise.resolve({ deploymentId })} />
      </TestProviders>,
    );

    await screen.findByRole("heading", { level: 2, name: /recent requests/i });
    expect(screen.getByText(/page 1 of 2/i)).toBeInTheDocument();

    const next = screen.getByRole("button", { name: /next page/i });
    await user.click(next);

    await waitFor(() => {
      expect(screen.getByText(/page 2 of 2/i)).toBeInTheDocument();
    });
  });

  it("shows the empty state when the recent requests list returns no items", async () => {
    apiMock.get.mockImplementation(async (path: string) => {
      if (path === `/deployments/${deploymentId}`) return baseDeployment;
      if (path === `/deployments/${deploymentId}/health`) return healthyHealth;
      if (path === `/deployments/${deploymentId}/metrics`) return metricsData;
      if (path === `/deployments/${deploymentId}/requests`) {
        return { items: [], total: 0, limit: 50, offset: 0 };
      }
      if (path === `/deployments/${deploymentId}/errors`) return errorsPage1;
      throw new Error(`unmocked GET ${path}`);
    });
    render(
      <TestProviders>
        <DeploymentMonitoringPage params={Promise.resolve({ deploymentId })} />
      </TestProviders>,
    );

    expect(await screen.findByText(/no requests recorded/i)).toBeInTheDocument();
  });

  it("shows the empty state when the recent errors list returns no items", async () => {
    apiMock.get.mockImplementation(async (path: string) => {
      if (path === `/deployments/${deploymentId}`) return baseDeployment;
      if (path === `/deployments/${deploymentId}/health`) return healthyHealth;
      if (path === `/deployments/${deploymentId}/metrics`) return metricsData;
      if (path === `/deployments/${deploymentId}/requests`) return requestsPage1;
      if (path === `/deployments/${deploymentId}/errors`) {
        return { items: [], total: 0, limit: 50, offset: 0 };
      }
      throw new Error(`unmocked GET ${path}`);
    });
    render(
      <TestProviders>
        <DeploymentMonitoringPage params={Promise.resolve({ deploymentId })} />
      </TestProviders>,
    );

    expect(await screen.findByText(/no errors recorded/i)).toBeInTheDocument();
  });

  it("renders the error table rows from the monitoring endpoint", async () => {
    mockAll();
    render(
      <TestProviders>
        <DeploymentMonitoringPage params={Promise.resolve({ deploymentId })} />
      </TestProviders>,
    );

    expect(await screen.findByText("INFERENCE_ERROR")).toBeInTheDocument();
    expect(screen.getByText("Adapter failed to load.")).toBeInTheDocument();
    expect(screen.getByText("409")).toBeInTheDocument();
  });

  it("does not paginate the requests list when total fits on one page", async () => {
    apiMock.get.mockImplementation(async (path: string) => {
      if (path === `/deployments/${deploymentId}`) return baseDeployment;
      if (path === `/deployments/${deploymentId}/health`) return healthyHealth;
      if (path === `/deployments/${deploymentId}/metrics`) return metricsData;
      if (path === `/deployments/${deploymentId}/requests`) {
        return { items: requestsPage1.items, total: 2, limit: 50, offset: 0 };
      }
      if (path === `/deployments/${deploymentId}/errors`) return { items: [], total: 0, limit: 50, offset: 0 };
      throw new Error(`unmocked GET ${path}`);
    });
    render(
      <TestProviders>
        <DeploymentMonitoringPage params={Promise.resolve({ deploymentId })} />
      </TestProviders>,
    );

    await screen.findByText(/no errors recorded/i);
    expect(screen.queryByRole("button", { name: /next page/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /previous page/i })).not.toBeInTheDocument();
  });
});
