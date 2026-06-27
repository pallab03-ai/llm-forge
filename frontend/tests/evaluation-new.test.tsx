import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import NewEvaluationPage from "@/app/(app)/evaluations/new/page";
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
  usePathname: () => "/evaluations/new",
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

const completedJob = {
  id: "00000000-0000-0000-0000-000000000020",
  user_id: "u-1",
  dataset_id: readyDatasetItem.id,
  dataset_version_id: "00000000-0000-0000-0000-0000000000a1",
  status: "completed" as const,
  base_model: "meta-llama/Meta-Llama-3.1-8B-Instruct",
  training_type: "lora" as const,
  configuration: { epochs: 3, batch_size: 4, learning_rate: 0.0002, max_seq_length: 512 },
  artifact_path: "/var/adapters/run-1",
  started_at: "2026-02-01T09:00:00Z",
  completed_at: "2026-02-01T10:00:00Z",
  error_message: null,
  created_at: "2026-02-01T09:00:00Z",
  updated_at: "2026-02-01T10:00:00Z",
};

const runningJob = { ...completedJob, id: "00000000-0000-0000-0000-000000000021", status: "running" as const, artifact_path: null };

const createdEvaluation = {
  id: "00000000-0000-0000-0000-000000000099",
  user_id: "u-1",
  dataset_id: readyDatasetItem.id,
  dataset_version_id: "00000000-0000-0000-0000-0000000000a1",
  model_id: completedJob.id,
  status: "running" as const,
  rouge_score: null,
  bertscore_precision: null,
  bertscore_recall: null,
  bertscore_f1: null,
  semantic_similarity: null,
  started_at: "2026-02-01T10:00:00Z",
  completed_at: null,
  error_message: null,
  created_at: "2026-02-01T10:00:00Z",
  updated_at: "2026-02-01T10:00:00Z",
};

function setupMocks() {
  apiMock.get.mockImplementation(async (path: string) => {
    if (path === "/training-jobs") {
      return { items: [completedJob, runningJob], total: 2, limit: 100, offset: 0 };
    }
    if (path === "/datasets") {
      return { items: [readyDatasetItem], total: 1, limit: 100, offset: 0 };
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

describe("NewEvaluationPage", () => {
  it("shows validation errors for missing required fields", async () => {
    setupMocks();
    const user = userEvent.setup();
    render(
      <TestProviders>
        <NewEvaluationPage />
      </TestProviders>,
    );

    const submit = await screen.findByRole("button", { name: /start evaluation/i });
    await user.click(submit);

    expect(await screen.findByText(/^choose a trained model\.$/i)).toBeInTheDocument();
    expect(await screen.findByText(/^choose a dataset\.$/i)).toBeInTheDocument();
    expect(apiMock.post).not.toHaveBeenCalled();
  });

  it("only shows completed training jobs with artifacts in the model select", async () => {
    setupMocks();
    render(
      <TestProviders>
        <NewEvaluationPage />
      </TestProviders>,
    );

    // ponytail: the rendered option text is "id.slice(0,8) · base_model", not
    // the full UUID. The id is "00000000-0000-0000-0000-000000000020", so the
    // slice is "00000000" (the first 8 chars). Match on the base_model
    // instead, which is unique and present in the option text.
    await screen.findByRole("option", { name: /Meta-Llama-3\.1-8B-Instruct/i });
    const select = screen.getByLabelText(/trained model/i) as HTMLSelectElement;
    const options = Array.from(select.querySelectorAll("option")).map((o) => o.textContent ?? "");
    expect(options.some((o) => o.includes("Meta-Llama-3.1-8B-Instruct"))).toBe(true);
    expect(options.some((o) => o.includes("00000000-0000-0000-0000-000000000021"))).toBe(false);
  });

  it("only shows ready datasets in the dataset select", async () => {
    apiMock.get.mockImplementation(async (path: string) => {
      if (path === "/training-jobs") return { items: [completedJob], total: 1, limit: 100, offset: 0 };
      if (path === "/datasets") {
        return {
          items: [
            readyDatasetItem,
            { ...readyDatasetItem, id: "00000000-0000-0000-0000-000000000002", name: "uploading-corpus", status: "uploading" as const },
          ],
          total: 2,
          limit: 100,
          offset: 0,
        };
      }
      if (path === `/datasets/${readyDatasetItem.id}`) return datasetDetail;
      throw new Error(`unmocked GET ${path}`);
    });
    render(
      <TestProviders>
        <NewEvaluationPage />
      </TestProviders>,
    );

    await screen.findByRole("option", { name: /ready-corpus/i });
    const select = screen.getByLabelText(/evaluation dataset/i) as HTMLSelectElement;
    const options = Array.from(select.querySelectorAll("option")).map((o) => o.textContent);
    expect(options).toContain("ready-corpus");
    expect(options).not.toContain("uploading-corpus");
  });

  it("auto-fills the dataset version when a dataset is picked", async () => {
    setupMocks();
    const user = userEvent.setup();
    apiMock.post.mockResolvedValue(createdEvaluation);
    render(
      <TestProviders>
        <NewEvaluationPage />
      </TestProviders>,
    );

    // ponytail: wait for the model <option> to exist (it is only added after
    // the training-jobs query resolves). selectOptions on a disabled <select>
    // silently does nothing.
    await screen.findByRole("option", { name: /Meta-Llama-3\.1-8B-Instruct/i });
    const modelSelect = screen.getByLabelText(/trained model/i) as HTMLSelectElement;
    await user.selectOptions(modelSelect, completedJob.id);
    const datasetSelect = screen.getByLabelText(/evaluation dataset/i) as HTMLSelectElement;
    await user.selectOptions(datasetSelect, readyDatasetItem.id);
    await screen.findByText(/v2/);

    await user.click(screen.getByRole("button", { name: /start evaluation/i }));

    await waitFor(() => {
      expect(apiMock.post).toHaveBeenCalledWith(
        "/evaluations",
        expect.objectContaining({
          model_id: completedJob.id,
          dataset_id: readyDatasetItem.id,
          dataset_version_id: "00000000-0000-0000-0000-0000000000a1",
        }),
      );
    });
    await waitFor(() => {
      expect(nav.push).toHaveBeenCalledWith(`/evaluations/${createdEvaluation.id}`);
    });
  });

  it("surfaces a backend validation error inline", async () => {
    setupMocks();
    apiMock.post.mockRejectedValue(
      new ApiError("MODEL_NOT_READY", "Trained model has no adapter artifact.", 409),
    );
    const user = userEvent.setup();
    render(
      <TestProviders>
        <NewEvaluationPage />
      </TestProviders>,
    );

    await screen.findByRole("option", { name: /Meta-Llama-3\.1-8B-Instruct/i });
    const modelSelect = screen.getByLabelText(/trained model/i) as HTMLSelectElement;
    await user.selectOptions(modelSelect, completedJob.id);
    await user.selectOptions(screen.getByLabelText(/evaluation dataset/i) as HTMLSelectElement, readyDatasetItem.id);
    await screen.findByText(/v2/);
    await user.click(screen.getByRole("button", { name: /start evaluation/i }));

    expect(await screen.findByText(/no adapter artifact/i)).toBeInTheDocument();
    expect(nav.push).not.toHaveBeenCalled();
  });
});
