import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Suspense } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ModelDetailPage from "@/app/(app)/models/[id]/page";
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
  usePathname: () => "/models/00000000-0000-0000-0000-000000000001",
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
      version_number: 2,
      artifact_path: "/var/adapters/run-2",
      metrics_snapshot: {
        rouge_score: 0.45,
        bertscore_precision: 0.82,
        bertscore_recall: 0.8,
        bertscore_f1: 0.81,
        semantic_similarity: 0.78,
      },
      status: "staging" as const,
      created_at: "2026-02-01T11:00:00Z",
      updated_at: "2026-02-01T11:00:00Z",
    },
    {
      id: "00000000-0000-0000-0000-0000000000a2",
      model_id: "00000000-0000-0000-0000-000000000001",
      training_job_id: "00000000-0000-0000-0000-0000000000b2",
      evaluation_id: "00000000-0000-0000-0000-0000000000c2",
      version_number: 1,
      artifact_path: "/var/adapters/run-1",
      metrics_snapshot: {
        rouge_score: 0.42,
        bertscore_precision: 0.81,
        bertscore_recall: 0.79,
        bertscore_f1: 0.8,
        semantic_similarity: 0.77,
      },
      status: "production" as const,
      created_at: "2026-02-01T10:00:00Z",
      updated_at: "2026-02-01T11:00:00Z",
    },
  ],
  created_at: "2026-02-01T10:00:00Z",
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

describe("ModelDetailPage", () => {
  it("renders header, info card, head-version metrics, and version history", async () => {
    apiMock.get.mockResolvedValue(baseModel);
    render(
      <TestProviders>
        <ModelDetailPage params={Promise.resolve({ id: baseModel.id })} />
      </TestProviders>,
    );

    expect(await screen.findByRole("heading", { level: 1, name: "customer-support-lora" })).toBeInTheDocument();
    // Head version is v2 (highest version_number); its metrics render.
    expect(screen.getByText("ROUGE-L")).toBeInTheDocument();
    expect(screen.getByText("0.4500")).toBeInTheDocument();
    // Version history lists both versions.
    expect(screen.getByText("v2")).toBeInTheDocument();
    expect(screen.getByText("v1")).toBeInTheDocument();
  });

  it("shows the not-found empty state on 404", async () => {
    apiMock.get.mockRejectedValue(new ApiError("NOT_FOUND", "Not found", 404));
    render(
      <TestProviders>
        <ModelDetailPage params={Promise.resolve({ id: "00000000-0000-0000-0000-0000000000ff" })} />
      </TestProviders>,
    );

    expect(await screen.findByText(/model not found/i)).toBeInTheDocument();
  });

  it("renders skeleton placeholders while loading", async () => {
    apiMock.get.mockImplementation(() => new Promise(() => {}));
    render(
      <TestProviders>
        <ModelDetailPage params={Promise.resolve({ id: baseModel.id })} />
      </TestProviders>,
    );

    await waitFor(() => {
      expect(document.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
    });
  });

  it("shows promote and archive buttons for staging versions and only archive for production", async () => {
    apiMock.get.mockResolvedValue(baseModel);
    render(
      <TestProviders>
        <ModelDetailPage params={Promise.resolve({ id: baseModel.id })} />
      </TestProviders>,
    );

    await screen.findByRole("heading", { level: 1, name: "customer-support-lora" });
    // v2 is staging → Promote + Archive.
    const promoteButtons = screen.getAllByRole("button", { name: /promote/i });
    const archiveButtons = screen.getAllByRole("button", { name: /archive/i });
    expect(promoteButtons).toHaveLength(1);
    expect(archiveButtons).toHaveLength(2);
  });

  it("calls POST /models/versions/{id}/promote when Promote is clicked", async () => {
    apiMock.get.mockResolvedValue(baseModel);
    apiMock.post.mockImplementation(async (path: string) => {
      if (path === "/models/versions/00000000-0000-0000-0000-0000000000a1/promote") {
        return { ...baseModel.versions[0], status: "production" as const };
      }
      throw new Error(`unmocked POST ${path}`);
    });
    const user = userEvent.setup();
    render(
      <TestProviders>
        <ModelDetailPage params={Promise.resolve({ id: baseModel.id })} />
      </TestProviders>,
    );

    const promote = await screen.findByRole("button", { name: /promote/i });
    await user.click(promote);

    await waitFor(() => {
      expect(apiMock.post).toHaveBeenCalledWith(
        "/models/versions/00000000-0000-0000-0000-0000000000a1/promote",
      );
    });
  });

  it("shows the no-versions empty state when the model has zero versions", async () => {
    apiMock.get.mockResolvedValue({ ...baseModel, versions: [] });
    render(
      <TestProviders>
        <ModelDetailPage params={Promise.resolve({ id: baseModel.id })} />
      </TestProviders>,
    );

    expect(await screen.findByText(/no versions yet/i)).toBeInTheDocument();
  });
});
