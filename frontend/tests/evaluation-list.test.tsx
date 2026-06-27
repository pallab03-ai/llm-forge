import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import EvaluationsPage from "@/app/(app)/evaluations/page";
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
  usePathname: () => "/evaluations",
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

const baseEvaluation = {
  id: "aaaa1111-0000-0000-0000-000000000001",
  user_id: "u-1",
  dataset_id: "00000000-0000-0000-0000-000000000010",
  dataset_version_id: "00000000-0000-0000-0000-000000000011",
  model_id: "00000000-0000-0000-0000-000000000020",
  status: "completed" as const,
  rouge_score: 0.42,
  bertscore_precision: 0.81,
  bertscore_recall: 0.79,
  bertscore_f1: 0.8,
  semantic_similarity: 0.77,
  started_at: "2026-02-01T10:00:00Z",
  completed_at: "2026-02-01T10:01:00Z",
  error_message: null,
  created_at: "2026-02-01T10:00:00Z",
  updated_at: "2026-02-01T10:01:00Z",
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

describe("EvaluationsPage", () => {
  it("renders rows from the API response", async () => {
    apiMock.get.mockResolvedValue({ items: [baseEvaluation], total: 1, limit: 100, offset: 0 });
    render(
      <TestProviders>
        <EvaluationsPage />
      </TestProviders>,
    );

    expect(await screen.findByText("aaaa1111")).toBeInTheDocument();
    expect(screen.getByText(baseEvaluation.id.slice(0, 8))).toBeInTheDocument();
    expect(screen.getAllByText("Completed").length).toBeGreaterThan(0);
  });

  it("filters rows client-side by search query", async () => {
    apiMock.get.mockResolvedValue({
      items: [
        baseEvaluation,
        { ...baseEvaluation, id: "bbbb2222-0000-0000-0000-000000000002", model_id: "00000000-0000-0000-0000-000000000099" },
      ],
      total: 2,
      limit: 100,
      offset: 0,
    });
    const user = userEvent.setup();
    render(
      <TestProviders>
        <EvaluationsPage />
      </TestProviders>,
    );

    await screen.findByText("aaaa1111");
    const search = screen.getByLabelText(/search evaluations/i);
    await user.type(search, "bbbb");

    await waitFor(() => {
      expect(screen.queryByText("aaaa1111")).not.toBeInTheDocument();
    });
    expect(screen.getByText("bbbb2222")).toBeInTheDocument();
  });

  it("shows the empty state when no evaluations exist", async () => {
    apiMock.get.mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 });
    render(
      <TestProviders>
        <EvaluationsPage />
      </TestProviders>,
    );

    expect(await screen.findByText(/no evaluations yet/i)).toBeInTheDocument();
    const links = screen.getAllByRole("link", { name: /new evaluation/i });
    expect(links[0]).toHaveAttribute("href", "/evaluations/new");
  });

  it("shows an error state when the list query fails", async () => {
    apiMock.get.mockRejectedValue(new ApiError("SERVER_ERROR", "Boom", 500));
    render(
      <TestProviders>
        <EvaluationsPage />
      </TestProviders>,
    );

    expect(await screen.findByText(/could not load evaluations/i)).toBeInTheDocument();
  });

  it("shows skeleton rows while loading", () => {
    apiMock.get.mockImplementation(() => new Promise(() => {}));
    render(
      <TestProviders>
        <EvaluationsPage />
      </TestProviders>,
    );

    expect(document.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
  });
});
