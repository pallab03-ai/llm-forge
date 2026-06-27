import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import RegisterModelPage from "@/app/(app)/models/register/page";
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
  usePathname: () => "/models/register",
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

const completedJob = {
  id: "00000000-0000-0000-0000-000000000010",
  user_id: "u-1",
  dataset_id: "00000000-0000-0000-0000-000000000020",
  dataset_version_id: "00000000-0000-0000-0000-000000000021",
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

const runningJob = { ...completedJob, id: "00000000-0000-0000-0000-000000000011", status: "running" as const, artifact_path: null };

const completedEvaluation = {
  id: "00000000-0000-0000-0000-000000000030",
  user_id: "u-1",
  dataset_id: "00000000-0000-0000-0000-000000000020",
  dataset_version_id: "00000000-0000-0000-0000-000000000021",
  model_id: completedJob.id,
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

const createdModel = {
  id: "00000000-0000-0000-0000-000000000040",
  owner_id: "u-1",
  name: "customer-support-lora",
  description: "QLoRA tuned for support replies",
  versions: [],
  created_at: "2026-02-01T11:00:00Z",
  updated_at: "2026-02-01T11:00:00Z",
};

const createdVersion = {
  id: "00000000-0000-0000-0000-000000000041",
  model_id: createdModel.id,
  training_job_id: completedJob.id,
  evaluation_id: completedEvaluation.id,
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
  created_at: "2026-02-01T11:00:00Z",
  updated_at: "2026-02-01T11:00:00Z",
};

function setupMocks() {
  apiMock.get.mockImplementation(async (path: string) => {
    if (path === "/training-jobs") {
      return { items: [completedJob, runningJob], total: 2, limit: 100, offset: 0 };
    }
    if (path === "/evaluations") {
      return { items: [completedEvaluation], total: 1, limit: 100, offset: 0 };
    }
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

describe("RegisterModelPage", () => {
  it("shows validation errors for missing required fields", async () => {
    setupMocks();
    const user = userEvent.setup();
    render(
      <TestProviders>
        <RegisterModelPage />
      </TestProviders>,
    );

    const submit = await screen.findByRole("button", { name: /register model/i });
    await user.click(submit);

    expect(await screen.findByText(/name is required\./i)).toBeInTheDocument();
    expect(apiMock.post).not.toHaveBeenCalled();
  });

  it("only shows completed training jobs with artifacts in the model select", async () => {
    setupMocks();
    render(
      <TestProviders>
        <RegisterModelPage />
      </TestProviders>,
    );

    await screen.findByRole("option", { name: /Meta-Llama-3\.1-8B-Instruct/i });
    const select = screen.getByLabelText(/training job/i) as HTMLSelectElement;
    const options = Array.from(select.querySelectorAll("option")).map((o) => o.textContent ?? "");
    expect(options.some((o) => o.includes("Meta-Llama-3.1-8B-Instruct"))).toBe(true);
    expect(options.some((o) => o.includes("00000000-0000-0000-0000-000000000011"))).toBe(false);
  });

  it("disables the evaluation select until a training job is picked", async () => {
    setupMocks();
    render(
      <TestProviders>
        <RegisterModelPage />
      </TestProviders>,
    );

    await screen.findByRole("option", { name: /Meta-Llama-3\.1-8B-Instruct/i });
    const evalSelect = screen.getByLabelText(/evaluation/i) as HTMLSelectElement;
    expect(evalSelect).toBeDisabled();
  });

  it("chains model create + version create and redirects to the detail page", async () => {
    setupMocks();
    apiMock.post.mockImplementation(async (path: string) => {
      if (path === "/models") return createdModel;
      if (path === `/models/${createdModel.id}/versions`) return createdVersion;
      throw new Error(`unmocked POST ${path}`);
    });
    const user = userEvent.setup();
    render(
      <TestProviders>
        <RegisterModelPage />
      </TestProviders>,
    );

    await user.type(screen.getByLabelText(/^name/i), "customer-support-lora");
    await user.type(screen.getByLabelText(/description/i), "QLoRA tuned for support replies");
    await screen.findByRole("option", { name: /Meta-Llama-3\.1-8B-Instruct/i });
    const jobSelect = screen.getByLabelText(/training job/i) as HTMLSelectElement;
    await user.selectOptions(jobSelect, completedJob.id);
    const evalSelect = screen.getByLabelText(/evaluation/i) as HTMLSelectElement;
    await user.selectOptions(evalSelect, completedEvaluation.id);
    await user.click(screen.getByRole("button", { name: /register model/i }));

    await waitFor(() => {
      expect(apiMock.post).toHaveBeenCalledWith(
        "/models",
        expect.objectContaining({ name: "customer-support-lora" }),
      );
    });
    await waitFor(() => {
      expect(apiMock.post).toHaveBeenCalledWith(
        `/models/${createdModel.id}/versions`,
        expect.objectContaining({
          training_job_id: completedJob.id,
          evaluation_id: completedEvaluation.id,
        }),
      );
    });
    await waitFor(() => {
      expect(nav.push).toHaveBeenCalledWith(`/models/${createdModel.id}`);
    });
  });

  it("surfaces a backend error from the model create inline", async () => {
    setupMocks();
    apiMock.post.mockRejectedValue(
      new ApiError("VALIDATION_FAILED", "Name must be 255 characters or fewer.", 422),
    );
    const user = userEvent.setup();
    render(
      <TestProviders>
        <RegisterModelPage />
      </TestProviders>,
    );

    await user.type(screen.getByLabelText(/^name/i), "x");
    await screen.findByRole("option", { name: /Meta-Llama-3\.1-8B-Instruct/i });
    const jobSelect = screen.getByLabelText(/training job/i) as HTMLSelectElement;
    await user.selectOptions(jobSelect, completedJob.id);
    const evalSelect = screen.getByLabelText(/evaluation/i) as HTMLSelectElement;
    await user.selectOptions(evalSelect, completedEvaluation.id);
    await user.click(screen.getByRole("button", { name: /register model/i }));

    expect(await screen.findByText(/name must be 255 characters/i)).toBeInTheDocument();
    expect(nav.push).not.toHaveBeenCalled();
  });

  it("surfaces a backend error from the version create inline without losing the model", async () => {
    setupMocks();
    apiMock.post.mockImplementation(async (path: string) => {
      if (path === "/models") return createdModel;
      if (path === `/models/${createdModel.id}/versions`) {
        throw new ApiError("EVALUATION_NOT_READY", "Evaluation is not completed.", 409);
      }
      throw new Error(`unmocked POST ${path}`);
    });
    const user = userEvent.setup();
    render(
      <TestProviders>
        <RegisterModelPage />
      </TestProviders>,
    );

    await user.type(screen.getByLabelText(/^name/i), "x");
    await screen.findByRole("option", { name: /Meta-Llama-3\.1-8B-Instruct/i });
    const jobSelect = screen.getByLabelText(/training job/i) as HTMLSelectElement;
    await user.selectOptions(jobSelect, completedJob.id);
    const evalSelect = screen.getByLabelText(/evaluation/i) as HTMLSelectElement;
    await user.selectOptions(evalSelect, completedEvaluation.id);
    await user.click(screen.getByRole("button", { name: /register model/i }));

    expect(await screen.findByText(/evaluation is not completed/i)).toBeInTheDocument();
    expect(nav.push).not.toHaveBeenCalled();
  });
});
