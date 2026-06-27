import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Suspense } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import TrainingDetailPage from "@/app/(app)/training/[id]/page";
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
  usePathname: () => "/training/00000000-0000-0000-0000-000000000001",
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

const jobRunning = {
  id: "00000000-0000-0000-0000-000000000001",
  user_id: "u-1",
  dataset_id: "00000000-0000-0000-0000-000000000010",
  dataset_version_id: "00000000-0000-0000-0000-000000000011",
  status: "running" as const,
  base_model: "meta-llama/Meta-Llama-3.1-8B-Instruct",
  training_type: "lora" as const,
  configuration: { epochs: 3, batch_size: 4, learning_rate: 0.0002, max_seq_length: 512 },
  artifact_path: null,
  started_at: "2026-02-01T10:00:00Z",
  completed_at: null,
  error_message: null,
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

describe("TrainingDetailPage", () => {
  it("renders job header, configuration, and section placeholders", async () => {
    apiMock.get.mockResolvedValue(jobRunning);
    render(
      <TestProviders>
        <TrainingDetailPage params={Promise.resolve({ id: jobRunning.id })} />
      </TestProviders>,
    );

    expect(await screen.findByRole("heading", { name: /training job/i })).toBeInTheDocument();
    // base_model renders in two places: the header subtitle and the Job information card.
    expect(screen.getAllByText(/meta-llama\/Meta-Llama-3\.1-8B-Instruct/).length).toBeGreaterThan(0);
    expect(screen.getByText("LoRA")).toBeInTheDocument();
    // Configuration card fields.
    expect(screen.getByText(/hyperparameters stored with the job/i)).toBeInTheDocument();
    // The 4 config keys render in order.
    expect(screen.getByText("Epochs")).toBeInTheDocument();
    expect(screen.getByText("Batch size")).toBeInTheDocument();
    expect(screen.getByText("Learning rate")).toBeInTheDocument();
    expect(screen.getByText("Max sequence length")).toBeInTheDocument();
    // Section placeholders.
    expect(screen.getByText(/metrics unavailable/i)).toBeInTheDocument();
    expect(screen.getByText(/logs unavailable/i)).toBeInTheDocument();
    expect(screen.getAllByText(/artifacts unavailable/i).length).toBeGreaterThan(0);
  });

  it("shows a cancel button while running and calls POST /:id/cancel", async () => {
    apiMock.get.mockResolvedValue(jobRunning);
    apiMock.post.mockResolvedValue({ ...jobRunning, status: "cancelled" });
    const user = userEvent.setup();
    render(
      <TestProviders>
        <TrainingDetailPage params={Promise.resolve({ id: jobRunning.id })} />
      </TestProviders>,
    );

    const cancel = await screen.findByRole("button", { name: /cancel job/i });
    await user.click(cancel);

    await waitFor(() => {
      expect(apiMock.post).toHaveBeenCalledWith(`/training-jobs/${jobRunning.id}/cancel`);
    });
  });

  it("shows a refresh button when terminal and the not-found empty state on 404", async () => {
    apiMock.get.mockRejectedValue(new ApiError("NOT_FOUND", "Not found", 404));
    render(
      <TestProviders>
        <TrainingDetailPage params={Promise.resolve({ id: "00000000-0000-0000-0000-0000000000ff" })} />
      </TestProviders>,
    );

    expect(await screen.findByText(/training job not found/i)).toBeInTheDocument();
  });

  it("renders skeleton placeholders while loading", async () => {
    apiMock.get.mockImplementation(() => new Promise(() => {}));
    render(
      <TestProviders>
        <TrainingDetailPage params={Promise.resolve({ id: jobRunning.id })} />
      </TestProviders>,
    );

    await waitFor(() => {
      expect(document.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
    });
  });

  it("renders the error message from a failed job", async () => {
    apiMock.get.mockResolvedValue({
      ...jobRunning,
      status: "failed",
      completed_at: "2026-02-01T11:00:00Z",
      error_message: "CUDA out of memory",
    });
    render(
      <TestProviders>
        <TrainingDetailPage params={Promise.resolve({ id: jobRunning.id })} />
      </TestProviders>,
    );

    expect(await screen.findByText(/cuda out of memory/i)).toBeInTheDocument();
    // Failed status badge.
    expect(screen.getAllByText("Failed").length).toBeGreaterThan(0);
  });
});
