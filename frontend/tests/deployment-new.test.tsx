import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Suspense } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import NewDeploymentPage from "@/app/(app)/deployments/new/page";
import { AuthProvider } from "@/providers/auth-provider";
import { ApiError } from "@/services/api-client";
import { authStorage } from "@/services/auth-storage";

const routerPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: routerPush,
    replace: vi.fn(),
    refresh: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => "/deployments/new",
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

const baseVersion = {
  id: "00000000-0000-0000-0000-0000000000a1",
  model_id: "00000000-0000-0000-0000-000000000001",
  training_job_id: "00000000-0000-0000-0000-0000000000b1",
  evaluation_id: "00000000-0000-0000-0000-0000000000c1",
  version_number: 1,
  artifact_path: "/var/adapters/run-1",
  metrics_snapshot: null,
  status: "staging" as const,
  created_at: "2026-02-01T10:00:00Z",
  updated_at: "2026-02-01T10:00:00Z",
};

const baseModel = {
  id: "00000000-0000-0000-0000-000000000001",
  owner_id: "u-1",
  name: "customer-support-lora",
  description: null,
  versions: [baseVersion],
  created_at: "2026-02-01T10:00:00Z",
  updated_at: "2026-02-01T10:00:00Z",
};

const baseDeployment = {
  id: "00000000-0000-0000-0000-0000000000d1",
  owner_id: "u-1",
  model_version_id: baseVersion.id,
  deployment_name: "support-bot",
  status: "pending" as const,
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
  routerPush.mockReset();
});

afterEach(() => {
  authStorage.clear();
});

describe("NewDeploymentPage", () => {
  it("shows validation errors for missing required fields", async () => {
    apiMock.get.mockResolvedValue({ items: [baseModel], total: 1, limit: 100, offset: 0 });
    const user = userEvent.setup();
    render(
      <TestProviders>
        <NewDeploymentPage />
      </TestProviders>,
    );

    await screen.findByRole("option", { name: /customer-support-lora/ });
    await user.click(screen.getByRole("button", { name: /create deployment/i }));

    expect(await screen.findByText(/choose a model version/i)).toBeInTheDocument();
    expect(screen.getByText(/deployment name is required/i)).toBeInTheDocument();
    expect(screen.getByText(/endpoint name is required/i)).toBeInTheDocument();
    expect(apiMock.post).not.toHaveBeenCalled();
  });

  it("filters out archived model versions in the select", async () => {
    apiMock.get.mockResolvedValue({
      items: [
        {
          ...baseModel,
          versions: [
            baseVersion,
            { ...baseVersion, id: "00000000-0000-0000-0000-0000000000a2", version_number: 2, status: "archived" as const },
          ],
        },
      ],
      total: 1,
      limit: 100,
      offset: 0,
    });
    render(
      <TestProviders>
        <NewDeploymentPage />
      </TestProviders>,
    );

    await screen.findByRole("option", { name: /v1 · staging/ });
    expect(screen.queryByRole("option", { name: /v2 · archived/ })).not.toBeInTheDocument();
  });

  it("submits valid data and redirects to the detail page", async () => {
    apiMock.get.mockResolvedValue({ items: [baseModel], total: 1, limit: 100, offset: 0 });
    apiMock.post.mockResolvedValue(baseDeployment);
    const user = userEvent.setup();
    render(
      <TestProviders>
        <NewDeploymentPage />
      </TestProviders>,
    );

    await screen.findByRole("option", { name: /customer-support-lora/ });
    await user.selectOptions(screen.getByLabelText(/model version/i), baseVersion.id);
    await user.type(screen.getByLabelText(/deployment name/i), "support-bot");
    await user.type(screen.getByLabelText(/endpoint name/i), "support-bot-v1");
    await user.click(screen.getByRole("button", { name: /create deployment/i }));

    await waitFor(() => {
      expect(apiMock.post).toHaveBeenCalledWith("/deployments", {
        model_version_id: baseVersion.id,
        deployment_name: "support-bot",
        endpoint_name: "support-bot-v1",
      });
    });
    await waitFor(() => {
      expect(routerPush).toHaveBeenCalledWith(`/deployments/${baseDeployment.id}`);
    });
  });

  it("surfaces a backend validation error inline", async () => {
    apiMock.get.mockResolvedValue({ items: [baseModel], total: 1, limit: 100, offset: 0 });
    apiMock.post.mockRejectedValue(new ApiError("MODEL_VERSION_ARCHIVED", "Model version is archived", 409));
    const user = userEvent.setup();
    render(
      <TestProviders>
        <NewDeploymentPage />
      </TestProviders>,
    );

    await screen.findByRole("option", { name: /customer-support-lora/ });
    await user.selectOptions(screen.getByLabelText(/model version/i), baseVersion.id);
    await user.type(screen.getByLabelText(/deployment name/i), "support-bot");
    await user.type(screen.getByLabelText(/endpoint name/i), "support-bot-v1");
    await user.click(screen.getByRole("button", { name: /create deployment/i }));

    expect(await screen.findByText(/model version is archived/i)).toBeInTheDocument();
  });

  it("shows a no-eligible-versions notice when no non-archived versions exist", async () => {
    apiMock.get.mockResolvedValue({
      items: [
        {
          ...baseModel,
          versions: [{ ...baseVersion, status: "archived" as const }],
        },
      ],
      total: 1,
      limit: 100,
      offset: 0,
    });
    render(
      <TestProviders>
        <NewDeploymentPage />
      </TestProviders>,
    );

    expect(await screen.findByText(/no eligible model versions/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create deployment/i })).toBeDisabled();
  });
});
