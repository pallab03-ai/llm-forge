import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import TrainingPage from "@/app/(app)/training/page";
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
  usePathname: () => "/training",
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

const baseJob = {
  id: "aaaa1111-0000-0000-0000-000000000001",
  user_id: "u-1",
  dataset_id: "00000000-0000-0000-0000-000000000010",
  dataset_version_id: "00000000-0000-0000-0000-000000000011",
  status: "running" as const,
  base_model: "meta-llama/Meta-Llama-3.1-8B-Instruct",
  training_type: "lora" as const,
  configuration: { epochs: 3, batch_size: 4, learning_rate: 0.0002, max_seq_length: 512 },
  artifact_path: null,
  started_at: null,
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

describe("TrainingPage", () => {
  it("renders rows from the API response", async () => {
    apiMock.get.mockResolvedValue({ items: [baseJob], total: 1, limit: 100, offset: 0 });
    render(
      <TestProviders>
        <TrainingPage />
      </TestProviders>,
    );

    expect(await screen.findByText("aaaa1111")).toBeInTheDocument();
    // The id is shortened to the first 8 chars; expect to find it.
    expect(screen.getByText(baseJob.id.slice(0, 8))).toBeInTheDocument();
    // Status badge label.
    expect(screen.getAllByText("Training").length).toBeGreaterThan(0);
  });

  it("filters rows client-side by search query", async () => {
    apiMock.get.mockResolvedValue({
      items: [
        baseJob,
        { ...baseJob, id: "bbbb2222-0000-0000-0000-000000000002", base_model: "mistralai/Mistral-7B-Instruct-v0.3" },
      ],
      total: 2,
      limit: 100,
      offset: 0,
    });
    const user = userEvent.setup();
    render(
      <TestProviders>
        <TrainingPage />
      </TestProviders>,
    );

    await screen.findByText("aaaa1111");
    const search = screen.getByLabelText(/search training jobs/i);
    await user.type(search, "mistral");

    await waitFor(() => {
      expect(screen.queryByText("aaaa1111")).not.toBeInTheDocument();
    });
    expect(screen.getByText("bbbb2222")).toBeInTheDocument();
  });

  it("shows the empty state when no jobs exist", async () => {
    apiMock.get.mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 });
    render(
      <TestProviders>
        <TrainingPage />
      </TestProviders>,
    );

    expect(await screen.findByText(/no training jobs yet/i)).toBeInTheDocument();
    const links = screen.getAllByRole("link", { name: /new training job/i });
    expect(links[0]).toHaveAttribute("href", "/training/new");
  });

  it("shows an error state when the list query fails", async () => {
    apiMock.get.mockRejectedValue(new ApiError("SERVER_ERROR", "Boom", 500));
    render(
      <TestProviders>
        <TrainingPage />
      </TestProviders>,
    );

    expect(await screen.findByText(/could not load training jobs/i)).toBeInTheDocument();
  });

  it("shows skeleton rows while loading", () => {
    apiMock.get.mockImplementation(() => new Promise(() => {}));
    render(
      <TestProviders>
        <TrainingPage />
      </TestProviders>,
    );

    expect(document.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
  });
});

// keep the `within` import in scope for future row-level assertions
void within;
