import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import DeploymentsPage from "@/app/(app)/deployments/page";
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
  usePathname: () => "/deployments",
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

const baseDeployment = {
  id: "00000000-0000-0000-0000-000000000001",
  owner_id: "u-1",
  model_version_id: "00000000-0000-0000-0000-0000000000a1",
  deployment_name: "support-bot",
  status: "active" as const,
  endpoint_name: "support-bot-v1",
  created_at: "2026-02-01T10:00:00Z",
  updated_at: "2026-02-01T10:00:00Z",
};

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

describe("DeploymentsPage", () => {
  it("renders rows from the API response", async () => {
    apiMock.get.mockResolvedValue({ items: [baseDeployment], total: 1, limit: 100, offset: 0 });
    render(
      <TestProviders>
        <DeploymentsPage />
      </TestProviders>,
    );

    expect(await screen.findByText("support-bot")).toBeInTheDocument();
    expect(screen.getByText("support-bot-v1")).toBeInTheDocument();
    expect(screen.getAllByText("Active").length).toBeGreaterThan(0);
  });

  it("filters rows client-side by search query", async () => {
    apiMock.get.mockResolvedValue({
      items: [
        baseDeployment,
        { ...baseDeployment, id: "00000000-0000-0000-0000-000000000002", deployment_name: "summarizer", endpoint_name: "summarizer-v1" },
      ],
      total: 2,
      limit: 100,
      offset: 0,
    });
    const user = userEvent.setup();
    render(
      <TestProviders>
        <DeploymentsPage />
      </TestProviders>,
    );

    await screen.findByText("support-bot");
    const search = screen.getByLabelText(/search deployments/i);
    await user.type(search, "summarizer");

    await waitFor(() => {
      expect(screen.queryByText("support-bot")).not.toBeInTheDocument();
    });
    expect(screen.getByText("summarizer")).toBeInTheDocument();
  });

  it("shows the empty state when no deployments exist", async () => {
    apiMock.get.mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 });
    render(
      <TestProviders>
        <DeploymentsPage />
      </TestProviders>,
    );

    expect(await screen.findByText(/no deployments yet/i)).toBeInTheDocument();
    const links = screen.getAllByRole("link", { name: /new deployment/i });
    expect(links[0]).toHaveAttribute("href", "/deployments/new");
  });

  it("shows an error state when the list query fails", async () => {
    apiMock.get.mockRejectedValue(new ApiError("SERVER_ERROR", "Boom", 500));
    render(
      <TestProviders>
        <DeploymentsPage />
      </TestProviders>,
    );

    expect(await screen.findByText(/could not load deployments/i)).toBeInTheDocument();
  });

  it("shows skeleton rows while loading", () => {
    apiMock.get.mockImplementation(() => new Promise(() => {}));
    render(
      <TestProviders>
        <DeploymentsPage />
      </TestProviders>,
    );

    expect(document.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
  });
});
