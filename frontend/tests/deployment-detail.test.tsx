import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Suspense } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import DeploymentDetailPage from "@/app/(app)/deployments/[id]/page";
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
  usePathname: () => "/deployments/00000000-0000-0000-0000-000000000001",
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

const baseDeployment = {
  id: "00000000-0000-0000-0000-0000000000d1",
  owner_id: "u-1",
  model_version_id: "00000000-0000-0000-0000-0000000000a1",
  deployment_name: "support-bot",
  status: "pending" as const,
  endpoint_name: "support-bot-v1",
  created_at: "2026-02-01T10:00:00Z",
  updated_at: "2026-02-01T10:00:00Z",
};

const activeDeployment = {
  ...baseDeployment,
  status: "active" as const,
  updated_at: "2026-02-01T11:00:00Z",
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

describe("DeploymentDetailPage", () => {
  it("renders header, info card, status, endpoint, playground, and history for a pending deployment", async () => {
    apiMock.get.mockResolvedValue(baseDeployment);
    render(
      <TestProviders>
        <DeploymentDetailPage params={Promise.resolve({ id: baseDeployment.id })} />
      </TestProviders>,
    );

    expect(await screen.findByRole("heading", { level: 1, name: "support-bot" })).toBeInTheDocument();
    expect(screen.getByText(/deployment information/i)).toBeInTheDocument();
    expect(screen.getByText(/inference playground/i)).toBeInTheDocument();
    expect(screen.getByText(/history/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /activate/i })).toBeInTheDocument();
  });

  it("does not show the activate button for active deployments", async () => {
    apiMock.get.mockResolvedValue(activeDeployment);
    render(
      <TestProviders>
        <DeploymentDetailPage params={Promise.resolve({ id: baseDeployment.id })} />
      </TestProviders>,
    );

    await screen.findByRole("heading", { level: 1, name: "support-bot" });
    expect(screen.queryByRole("button", { name: /activate/i })).not.toBeInTheDocument();
  });

  it("calls POST /deployments/{id}/activate when Activate is clicked", async () => {
    apiMock.get.mockResolvedValue(baseDeployment);
    apiMock.post.mockImplementation(async (path: string) => {
      if (path === "/deployments/00000000-0000-0000-0000-0000000000d1/activate") {
        return { ...baseDeployment, status: "active" as const };
      }
      throw new Error(`unmocked POST ${path}`);
    });
    const user = userEvent.setup();
    render(
      <TestProviders>
        <DeploymentDetailPage params={Promise.resolve({ id: baseDeployment.id })} />
      </TestProviders>,
    );

    const activate = await screen.findByRole("button", { name: /activate/i });
    await user.click(activate);

    await waitFor(() => {
      expect(apiMock.post).toHaveBeenCalledWith(
        "/deployments/00000000-0000-0000-0000-0000000000d1/activate",
      );
    });
  });

  it("shows the not-found empty state on 404", async () => {
    apiMock.get.mockRejectedValue(new ApiError("NOT_FOUND", "Not found", 404));
    render(
      <TestProviders>
        <DeploymentDetailPage params={Promise.resolve({ id: "00000000-0000-0000-0000-0000000000ff" })} />
      </TestProviders>,
    );

    expect(await screen.findByText(/deployment not found/i)).toBeInTheDocument();
  });

  it("renders skeleton placeholders while loading", async () => {
    apiMock.get.mockImplementation(() => new Promise(() => {}));
    render(
      <TestProviders>
        <DeploymentDetailPage params={Promise.resolve({ id: baseDeployment.id })} />
      </TestProviders>,
    );

    await waitFor(() => {
      expect(document.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
    });
  });

  it("runs a generation request and renders the response on an active deployment", async () => {
    apiMock.get.mockResolvedValue(activeDeployment);
    apiMock.post.mockImplementation(async (path: string, body: { prompt?: string }) => {
      if (path === "/deployments/00000000-0000-0000-0000-0000000000d1/generate") {
        return { response: `Echo: ${body?.prompt ?? ""}` };
      }
      throw new Error(`unmocked POST ${path}`);
    });
    const user = userEvent.setup();
    render(
      <TestProviders>
        <DeploymentDetailPage params={Promise.resolve({ id: baseDeployment.id })} />
      </TestProviders>,
    );

    await screen.findByRole("heading", { level: 1, name: "support-bot" });
    const prompt = screen.getByLabelText(/^prompt$/i);
    await user.type(prompt, "Hello, world.");
    await user.click(screen.getByRole("button", { name: /generate/i }));

    await waitFor(() => {
      expect(apiMock.post).toHaveBeenCalledWith(
        "/deployments/00000000-0000-0000-0000-0000000000d1/generate",
        { prompt: "Hello, world." },
      );
    });
    expect(await screen.findByText("Echo: Hello, world.")).toBeInTheDocument();
  });

  it("shows a Copy button after a successful generation", async () => {
    apiMock.get.mockResolvedValue(activeDeployment);
    apiMock.post.mockImplementation(async (path: string) => {
      if (path === "/deployments/00000000-0000-0000-0000-0000000000d1/generate") {
        return { response: "The model said hi." };
      }
      throw new Error(`unmocked POST ${path}`);
    });
    const user = userEvent.setup();
    render(
      <TestProviders>
        <DeploymentDetailPage params={Promise.resolve({ id: baseDeployment.id })} />
      </TestProviders>,
    );

    await screen.findByRole("heading", { level: 1, name: "support-bot" });
    await user.type(screen.getByLabelText(/^prompt$/i), "Hi");
    await user.click(screen.getByRole("button", { name: /generate/i }));

    expect(await screen.findByRole("button", { name: /copy/i })).toBeInTheDocument();
    expect(await screen.findByText("The model said hi.")).toBeInTheDocument();
  });

  it("shows a not-active message in the playground for non-active deployments", async () => {
    apiMock.get.mockResolvedValue(baseDeployment);
    render(
      <TestProviders>
        <DeploymentDetailPage params={Promise.resolve({ id: baseDeployment.id })} />
      </TestProviders>,
    );

    await screen.findByRole("heading", { level: 1, name: "support-bot" });
    expect(screen.getByText(/the deployment is pending/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/^prompt$/i)).not.toBeInTheDocument();
  });
});
