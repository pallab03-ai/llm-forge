import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import DatasetsPage from "@/app/(app)/datasets/page";
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
  usePathname: () => "/datasets",
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

const baseDataset = {
  id: "ds-1",
  name: "my-corpus",
  description: "A test dataset",
  dataset_type: "instruction_tuning" as const,
  format: "jsonl" as const,
  status: "ready" as const,
  created_by: "user-1",
  created_at: "2026-01-15T10:00:00Z",
  updated_at: "2026-01-15T10:00:00Z",
};

function happyList(items: typeof baseDataset[] = [baseDataset]) {
  apiMock.get.mockResolvedValue({ items, total: items.length, limit: 100, offset: 0 });
}

beforeEach(() => {
  authStorage.clear();
  authStorage.setToken({ accessToken: "tok", tokenType: "bearer", expiresAt: Date.now() + 60_000 });
  authStorage.setUser({ id: "u-1", email: "ada@example.com", username: "ada", role: "user" });
  apiMock.get.mockReset();
  nav.push.mockReset();
});

afterEach(() => {
  authStorage.clear();
});

describe("DatasetsPage", () => {
  it("renders rows from the API response", async () => {
    happyList();
    render(
      <TestProviders>
        <DatasetsPage />
      </TestProviders>,
    );

    expect(await screen.findByRole("link", { name: /my-corpus/i })).toBeInTheDocument();
    expect(apiMock.get).toHaveBeenCalledWith("/datasets");
  });

  it("filters rows client-side by search query", async () => {
    happyList([
      baseDataset,
      { ...baseDataset, id: "ds-2", name: "chat-eval" },
    ]);
    const user = userEvent.setup();
    render(
      <TestProviders>
        <DatasetsPage />
      </TestProviders>,
    );

    await screen.findByRole("link", { name: /my-corpus/i });

    const search = screen.getByLabelText(/search datasets by name/i);
    await user.type(search, "chat");

    await waitFor(() => {
      expect(screen.queryByRole("link", { name: /my-corpus/i })).not.toBeInTheDocument();
    });
    expect(screen.getByRole("link", { name: /chat-eval/i })).toBeInTheDocument();
  });

  it("shows the empty state when the API returns no items", async () => {
    happyList([]);
    render(
      <TestProviders>
        <DatasetsPage />
      </TestProviders>,
    );

    expect(await screen.findByText(/no datasets yet/i)).toBeInTheDocument();
    const uploadLinks = screen.getAllByRole("link", { name: /upload dataset/i });
    expect(uploadLinks.length).toBeGreaterThan(0);
    expect(uploadLinks[0]).toHaveAttribute("href", "/datasets/upload");
  });

  it("shows an error state when the list query fails", async () => {
    apiMock.get.mockRejectedValue(new ApiError("SERVER_ERROR", "Boom", 500));
    render(
      <TestProviders>
        <DatasetsPage />
      </TestProviders>,
    );

    expect(await screen.findByText(/could not load datasets/i)).toBeInTheDocument();
  });

  it("shows skeleton rows while loading", () => {
    apiMock.get.mockImplementation(() => new Promise(() => {}));
    render(
      <TestProviders>
        <DatasetsPage />
      </TestProviders>,
    );

    const skeletons = document.querySelectorAll(".animate-pulse");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("renders a link to the upload page in the header", async () => {
    happyList();
    render(
      <TestProviders>
        <DatasetsPage />
      </TestProviders>,
    );

    await waitFor(() => {
      const links = screen.getAllByRole("link", { name: /upload dataset/i });
      expect(links.length).toBeGreaterThan(0);
    });
    const firstLink = screen.getAllByRole("link", { name: /upload dataset/i })[0];
    expect(firstLink).toHaveAttribute("href", "/datasets/upload");
  });
});

// keep the `within` import in scope for future row-level assertions
void within;
