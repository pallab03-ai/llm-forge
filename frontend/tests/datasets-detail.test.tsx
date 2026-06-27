import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { Suspense } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import DatasetDetailPage from "@/app/(app)/datasets/[id]/page";
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
  usePathname: () => "/datasets/ds-1",
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
  // ponytail: the page calls `use(params)`, which suspends until the params
  // promise settles. In Next.js the framework provides a Suspense boundary;
  // in tests we add one ourselves so the first paint is not a thrown promise.
  return (
    <QueryClientProvider client={client}>
      <AuthProvider>
        <Suspense fallback={<div data-testid="page-suspense">Loading</div>}>
          {children}
        </Suspense>
      </AuthProvider>
    </QueryClientProvider>
  );
}

const versionWithErrors = {
  id: "v-1",
  dataset_id: "ds-1",
  version_number: 2,
  file_size_bytes: 2048,
  record_count: 50,
  duplicate_count: 3,
  validation_errors: JSON.stringify([
    { code: "EMPTY_PROMPT", severity: "warning", message: "3 empty prompts detected" },
    { code: "SCHEMA_MISMATCH", severity: "fail", message: "Row 12 is missing the 'response' field" },
  ]),
  statistics: null,
  created_at: "2026-01-15T10:00:00Z",
  updated_at: "2026-01-15T10:00:00Z",
};

const versionClean = {
  ...versionWithErrors,
  id: "v-0",
  version_number: 1,
  record_count: 10,
  duplicate_count: 0,
  validation_errors: null,
  created_at: "2026-01-10T10:00:00Z",
};

const datasetDetail = {
  id: "ds-1",
  name: "instruction-tuning-corpus",
  description: "A corpus of instruction/response pairs.",
  dataset_type: "instruction_tuning",
  format: "jsonl",
  status: "ready",
  created_by: "u-1",
  created_at: "2026-01-10T10:00:00Z",
  updated_at: "2026-01-15T10:00:00Z",
  versions: [versionWithErrors, versionClean],
};

beforeEach(() => {
  authStorage.clear();
  authStorage.setToken({ accessToken: "tok", tokenType: "bearer", expiresAt: Date.now() + 60_000 });
  authStorage.setUser({ id: "u-1", email: "ada@example.com", username: "ada", role: "user" });
  apiMock.get.mockReset();
});

afterEach(() => {
  authStorage.clear();
});

describe("DatasetDetailPage", () => {
  it("renders the dataset header, metadata, and version table", async () => {
    apiMock.get.mockResolvedValue(datasetDetail);
    render(
      <TestProviders>
        <DatasetDetailPage params={Promise.resolve({ id: "ds-1" })} />
      </TestProviders>,
    );

    expect(await screen.findByRole("heading", { name: /instruction-tuning-corpus/i })).toBeInTheDocument();
    expect(screen.getAllByText(/A corpus of instruction\/response pairs\./i).length).toBeGreaterThan(0);
    // v2 is the latest; both versions should appear in the table.
    expect(screen.getAllByText(/v2/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/v1/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Latest/i).length).toBeGreaterThan(0);
  });

  it("renders the validation summary from the latest version", async () => {
    apiMock.get.mockResolvedValue(datasetDetail);
    render(
      <TestProviders>
        <DatasetDetailPage params={Promise.resolve({ id: "ds-1" })} />
      </TestProviders>,
    );

    await screen.findByRole("heading", { name: /instruction-tuning-corpus/i });
    expect(screen.getByText(/3 empty prompts detected/i)).toBeInTheDocument();
    expect(screen.getByText(/Row 12 is missing the 'response' field/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Warning/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Fail/i).length).toBeGreaterThan(0);
  });

  it("shows the not-found empty state for a 404", async () => {
    apiMock.get.mockRejectedValue(new ApiError("NOT_FOUND", "Not found", 404));
    render(
      <TestProviders>
        <DatasetDetailPage params={Promise.resolve({ id: "ds-missing" })} />
      </TestProviders>,
    );

    expect(await screen.findByText(/dataset not found/i)).toBeInTheDocument();
  });

  it("shows a friendly error state for a network failure", async () => {
    apiMock.get.mockRejectedValue(new TypeError("NetworkError"));
    render(
      <TestProviders>
        <DatasetDetailPage params={Promise.resolve({ id: "ds-1" })} />
      </TestProviders>,
    );

    expect(await screen.findByText(/could not load dataset/i)).toBeInTheDocument();
  });

  it("renders skeleton placeholders while the query is loading", async () => {
    apiMock.get.mockImplementation(() => new Promise(() => {}));
    render(
      <TestProviders>
        <DatasetDetailPage params={Promise.resolve({ id: "ds-1" })} />
      </TestProviders>,
    );

    await waitFor(() => {
      expect(document.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
    });
  });

  it("links to the version upload page from the header", async () => {
    apiMock.get.mockResolvedValue(datasetDetail);
    render(
      <TestProviders>
        <DatasetDetailPage params={Promise.resolve({ id: "ds-1" })} />
      </TestProviders>,
    );

    const link = await screen.findByRole("link", { name: /upload new version/i });
    expect(link).toHaveAttribute("href", "/datasets/upload?datasetId=ds-1");
  });

  it("links back to the list page", async () => {
    apiMock.get.mockResolvedValue(datasetDetail);
    render(
      <TestProviders>
        <DatasetDetailPage params={Promise.resolve({ id: "ds-1" })} />
      </TestProviders>,
    );

    const back = await screen.findByRole("link", { name: /all datasets/i });
    expect(back).toHaveAttribute("href", "/datasets");
  });

  it("renders an empty versions section when no versions exist", async () => {
    apiMock.get.mockResolvedValue({ ...datasetDetail, versions: [] });
    render(
      <TestProviders>
        <DatasetDetailPage params={Promise.resolve({ id: "ds-1" })} />
      </TestProviders>,
    );

    await waitFor(() => {
      expect(screen.getAllByText(/no versions yet/i).length).toBeGreaterThan(0);
    });
  });
});
