import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { Suspense } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import EvaluationDetailPage from "@/app/(app)/evaluations/[id]/page";
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
  usePathname: () => "/evaluations/00000000-0000-0000-0000-000000000001",
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

const completedEvaluation = {
  id: "00000000-0000-0000-0000-000000000001",
  user_id: "u-1",
  dataset_id: "00000000-0000-0000-0000-000000000010",
  dataset_version_id: "00000000-0000-0000-0000-000000000011",
  model_id: "00000000-0000-0000-0000-000000000020",
  status: "completed" as const,
  rouge_score: 0.4217,
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

describe("EvaluationDetailPage", () => {
  it("renders header, info card, metrics, summary, and section placeholders", async () => {
    apiMock.get.mockResolvedValue(completedEvaluation);
    render(
      <TestProviders>
        <EvaluationDetailPage params={Promise.resolve({ id: completedEvaluation.id })} />
      </TestProviders>,
    );

    // ponytail: the h1 says "Evaluation 00000000", the info card has an h3
    // that also contains "Evaluation". Match the h1 by level so we don't
    // trip over the "Evaluation information" card title.
    expect(
      await screen.findByRole("heading", { level: 1, name: /evaluation/i }),
    ).toBeInTheDocument();
    // The 5 metric labels render in order.
    expect(screen.getByText("ROUGE-L")).toBeInTheDocument();
    expect(screen.getByText("BERTScore Precision")).toBeInTheDocument();
    expect(screen.getByText("BERTScore Recall")).toBeInTheDocument();
    expect(screen.getByText("BERTScore F1")).toBeInTheDocument();
    expect(screen.getByText("Semantic Similarity")).toBeInTheDocument();
    // ROUGE-L formatted to 4 decimals.
    expect(screen.getByText("0.4217")).toBeInTheDocument();
    // Section placeholders.
    expect(screen.getByText(/raw results unavailable/i)).toBeInTheDocument();
    expect(screen.getByText(/comparison unavailable/i)).toBeInTheDocument();
  });

  it("renders an em-dash for every metric when none are computed", async () => {
    apiMock.get.mockResolvedValue({ ...completedEvaluation, status: "running", rouge_score: null, bertscore_precision: null, bertscore_recall: null, bertscore_f1: null, semantic_similarity: null });
    render(
      <TestProviders>
        <EvaluationDetailPage params={Promise.resolve({ id: completedEvaluation.id })} />
      </TestProviders>,
    );

    expect(await screen.findByText("ROUGE-L")).toBeInTheDocument();
    const dashes = screen.getAllByText("—");
    // 5 metric em-dashes + the em-dashes used for missing dates.
    expect(dashes.length).toBeGreaterThanOrEqual(5);
  });

  it("shows the not-found empty state on 404", async () => {
    apiMock.get.mockRejectedValue(new ApiError("NOT_FOUND", "Not found", 404));
    render(
      <TestProviders>
        <EvaluationDetailPage params={Promise.resolve({ id: "00000000-0000-0000-0000-0000000000ff" })} />
      </TestProviders>,
    );

    expect(await screen.findByText(/evaluation not found/i)).toBeInTheDocument();
  });

  it("renders skeleton placeholders while loading", async () => {
    apiMock.get.mockImplementation(() => new Promise(() => {}));
    render(
      <TestProviders>
        <EvaluationDetailPage params={Promise.resolve({ id: completedEvaluation.id })} />
      </TestProviders>,
    );

    await waitFor(() => {
      expect(document.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
    });
  });

  it("renders the error message from a failed evaluation", async () => {
    apiMock.get.mockResolvedValue({
      ...completedEvaluation,
      status: "failed",
      completed_at: "2026-02-01T10:01:00Z",
      error_message: "Adapter not found at path: /var/adapters/missing",
    });
    render(
      <TestProviders>
        <EvaluationDetailPage params={Promise.resolve({ id: completedEvaluation.id })} />
      </TestProviders>,
    );

    expect(await screen.findByText(/adapter not found at path/i)).toBeInTheDocument();
    expect(screen.getAllByText("Failed").length).toBeGreaterThan(0);
  });
});
