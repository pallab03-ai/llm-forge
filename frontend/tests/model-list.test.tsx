import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ModelsPage from "@/app/(app)/models/page";
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
  usePathname: () => "/models",
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

const baseModel = {
  id: "00000000-0000-0000-0000-000000000001",
  owner_id: "u-1",
  name: "customer-support-lora",
  description: "QLoRA tuned for support replies",
  versions: [
    {
      id: "00000000-0000-0000-0000-0000000000a1",
      model_id: "00000000-0000-0000-0000-000000000001",
      training_job_id: "00000000-0000-0000-0000-0000000000b1",
      evaluation_id: "00000000-0000-0000-0000-0000000000c1",
      version_number: 1,
      artifact_path: "/var/adapters/run-1",
      metrics_snapshot: {
        rouge_score: 0.42,
        bertscore_precision: 0.81,
        bertscore_recall: 0.79,
        bertscore_f1: 0.8,
        semantic_similarity: 0.77,
      },
      status: "staging" as const,
      created_at: "2026-02-01T10:00:00Z",
      updated_at: "2026-02-01T10:00:00Z",
    },
  ],
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

describe("ModelsPage", () => {
  it("renders rows from the API response", async () => {
    apiMock.get.mockResolvedValue({ items: [baseModel], total: 1, limit: 100, offset: 0 });
    render(
      <TestProviders>
        <ModelsPage />
      </TestProviders>,
    );

    expect(await screen.findByText("customer-support-lora")).toBeInTheDocument();
    expect(screen.getByText("v1")).toBeInTheDocument();
    expect(screen.getAllByText("Staging").length).toBeGreaterThan(0);
  });

  it("filters rows client-side by search query", async () => {
    apiMock.get.mockResolvedValue({
      items: [
        baseModel,
        { ...baseModel, id: "00000000-0000-0000-0000-000000000002", name: "summarizer" },
      ],
      total: 2,
      limit: 100,
      offset: 0,
    });
    const user = userEvent.setup();
    render(
      <TestProviders>
        <ModelsPage />
      </TestProviders>,
    );

    await screen.findByText("customer-support-lora");
    const search = screen.getByLabelText(/search models/i);
    await user.type(search, "summarizer");

    await waitFor(() => {
      expect(screen.queryByText("customer-support-lora")).not.toBeInTheDocument();
    });
    expect(screen.getByText("summarizer")).toBeInTheDocument();
  });

  it("shows the empty state when no models exist", async () => {
    apiMock.get.mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 });
    render(
      <TestProviders>
        <ModelsPage />
      </TestProviders>,
    );

    expect(await screen.findByText(/no registered models yet/i)).toBeInTheDocument();
    const links = screen.getAllByRole("link", { name: /register model/i });
    expect(links[0]).toHaveAttribute("href", "/models/register");
  });

  it("shows an error state when the list query fails", async () => {
    apiMock.get.mockRejectedValue(new ApiError("SERVER_ERROR", "Boom", 500));
    render(
      <TestProviders>
        <ModelsPage />
      </TestProviders>,
    );

    expect(await screen.findByText(/could not load models/i)).toBeInTheDocument();
  });

  it("shows skeleton rows while loading", () => {
    apiMock.get.mockImplementation(() => new Promise(() => {}));
    render(
      <TestProviders>
        <ModelsPage />
      </TestProviders>,
    );

    expect(document.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
  });
});
