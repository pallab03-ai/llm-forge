import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import NewTrainingJobPage from "@/app/(app)/training/new/page";
import { AuthProvider } from "@/providers/auth-provider";
import { ApiError } from "@/services/api-client";
import { authStorage } from "@/services/auth-storage";

const nav = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
  back: vi.fn(),
  forward: vi.fn(),
  prefetch: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => nav,
  usePathname: () => "/training/new",
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

const readyDatasetItem = {
  id: "00000000-0000-0000-0000-000000000001",
  name: "ready-corpus",
  description: null,
  dataset_type: "instruction_tuning" as const,
  format: "jsonl" as const,
  status: "ready" as const,
  created_by: "u-1",
  created_at: "2026-01-15T10:00:00Z",
  updated_at: "2026-01-15T10:00:00Z",
};

const uploadingDataset = { ...readyDatasetItem, id: "00000000-0000-0000-0000-000000000002", name: "uploading-corpus", status: "uploading" as const };

const datasetDetail = {
  ...readyDatasetItem,
  versions: [
    {
      id: "00000000-0000-0000-0000-0000000000a1",
      dataset_id: readyDatasetItem.id,
      version_number: 2,
      file_size_bytes: 4096,
      record_count: 100,
      duplicate_count: 0,
      validation_errors: null,
      statistics: null,
      created_at: "2026-01-15T10:00:00Z",
      updated_at: "2026-01-15T10:00:00Z",
    },
  ],
};

const createdJob = {
  id: "00000000-0000-0000-0000-000000000099",
  user_id: "u-1",
  dataset_id: readyDatasetItem.id,
  dataset_version_id: "00000000-0000-0000-0000-0000000000a1",
  status: "queued" as const,
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

function setupDatasetMocks() {
  apiMock.get.mockImplementation(async (path: string) => {
    if (path === "/datasets") {
      return { items: [readyDatasetItem, uploadingDataset], total: 2, limit: 100, offset: 0 };
    }
    if (path === `/datasets/${readyDatasetItem.id}`) return datasetDetail;
    throw new Error(`unmocked GET ${path}`);
  });
}

beforeEach(() => {
  authStorage.clear();
  authStorage.setToken({ accessToken: "tok", tokenType: "bearer", expiresAt: Date.now() + 60_000 });
  authStorage.setUser({ id: "u-1", email: "ada@example.com", username: "ada", role: "user" });
  apiMock.get.mockReset();
  apiMock.post.mockReset();
  nav.push.mockReset();
});

afterEach(() => {
  authStorage.clear();
});

describe("NewTrainingJobPage", () => {
  it("shows validation errors for missing required fields", async () => {
    setupDatasetMocks();
    const user = userEvent.setup();
    render(
      <TestProviders>
        <NewTrainingJobPage />
      </TestProviders>,
    );

    // No file is involved; click submit with empty name + base_model.
    const submit = await screen.findByRole("button", { name: /create training job/i });
    await user.click(submit);

    expect(await screen.findByText(/job name is required/i)).toBeInTheDocument();
    expect(await screen.findByText(/base model is required/i)).toBeInTheDocument();
    expect(apiMock.post).not.toHaveBeenCalled();
  });

  it("lists only ready datasets in the dataset select", async () => {
    setupDatasetMocks();
    render(
      <TestProviders>
        <NewTrainingJobPage />
      </TestProviders>,
    );

    // wait for the options to appear
    await screen.findByRole("option", { name: /ready-corpus/i });
    const select = (screen.getByLabelText(/dataset/i)) as HTMLSelectElement;
    const options = Array.from(select.querySelectorAll("option")).map((o) => o.textContent);
    expect(options).toContain("ready-corpus");
    expect(options).not.toContain("uploading-corpus");
  });

  it("rejects an out-of-range epoch value", async () => {
    setupDatasetMocks();
    const user = userEvent.setup();
    render(
      <TestProviders>
        <NewTrainingJobPage />
      </TestProviders>,
    );

    const epochs = (await screen.findByLabelText(/^epochs$/i)) as HTMLInputElement;
    await user.clear(epochs);
    await user.type(epochs, "999");
    await user.click(screen.getByRole("button", { name: /create training job/i }));

    expect(await screen.findByText(/epochs must be at most 10/i)).toBeInTheDocument();
  });

  it("rejects an OOM-risky batch_size * max_seq_length combination", async () => {
    setupDatasetMocks();
    const user = userEvent.setup();
    render(
      <TestProviders>
        <NewTrainingJobPage />
      </TestProviders>,
    );

    const batch = (await screen.findByLabelText(/batch size/i)) as HTMLInputElement;
    const seq = (await screen.findByLabelText(/max sequence length/i)) as HTMLInputElement;
    await user.clear(batch);
    await user.type(batch, "64");
    await user.clear(seq);
    await user.type(seq, "8192");
    await user.click(screen.getByRole("button", { name: /create training job/i }));

    expect(await screen.findByText(/at most 262144/i)).toBeInTheDocument();
  });

  it("submits a valid job and redirects to the detail page", async () => {
    setupDatasetMocks();
    apiMock.post.mockResolvedValue(createdJob);
    const user = userEvent.setup();
    render(
      <TestProviders>
        <NewTrainingJobPage />
      </TestProviders>,
    );

    await user.type(screen.getByLabelText(/job name/i), "instruction-tune-1");
    await user.type(screen.getByLabelText(/base model/i), "meta-llama/Meta-Llama-3.1-8B-Instruct");
    const select = screen.getByLabelText(/dataset/i) as HTMLSelectElement;
    await user.selectOptions(select, readyDatasetItem.id);
    // wait for dataset detail fetch
    await screen.findByText(/v2/);
    await user.click(screen.getByRole("button", { name: /create training job/i }));

    await waitFor(() => {
      expect(apiMock.post).toHaveBeenCalledWith(
        "/training-jobs",
        expect.objectContaining({
          dataset_id: readyDatasetItem.id,
          training_type: "lora",
        }),
      );
    });
    await waitFor(() => {
      expect(nav.push).toHaveBeenCalledWith(`/training/${createdJob.id}`);
    });
  });

  it("surfaces a backend validation error inline", async () => {
    setupDatasetMocks();
    apiMock.post.mockRejectedValue(
      new ApiError("VALIDATION_FAILED", "Learning rate is out of range", 422),
    );
    const user = userEvent.setup();
    render(
      <TestProviders>
        <NewTrainingJobPage />
      </TestProviders>,
    );

    await user.type(screen.getByLabelText(/job name/i), "broken");
    await user.type(screen.getByLabelText(/base model/i), "x");
    await user.selectOptions(screen.getByLabelText(/dataset/i) as HTMLSelectElement, readyDatasetItem.id);
    await screen.findByText(/v2/);
    await user.click(screen.getByRole("button", { name: /create training job/i }));

    expect(await screen.findByText(/learning rate is out of range/i)).toBeInTheDocument();
    expect(nav.push).not.toHaveBeenCalled();
  });
});
