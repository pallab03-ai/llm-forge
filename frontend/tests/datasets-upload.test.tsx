import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import UploadDatasetPage from "@/app/(app)/datasets/upload/page";
import { AuthProvider } from "@/providers/auth-provider";
import { ApiError, uploadFile } from "@/services/api-client";
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
  usePathname: () => "/datasets/upload",
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

const searchParams = Promise.resolve({} as { datasetId?: string });

const datasetDetail = {
  id: "ds-1",
  name: "my-corpus",
  description: null,
  dataset_type: "instruction_tuning",
  format: "jsonl",
  status: "ready",
  created_by: "u-1",
  created_at: "2026-01-15T10:00:00Z",
  updated_at: "2026-01-15T10:00:00Z",
  versions: [
    {
      id: "v-1",
      dataset_id: "ds-1",
      version_number: 1,
      file_size_bytes: 1024,
      record_count: 10,
      duplicate_count: 0,
      validation_errors: null,
      statistics: null,
      created_at: "2026-01-15T10:00:00Z",
      updated_at: "2026-01-15T10:00:00Z",
    },
  ],
};

function makeFile(name = "corpus.jsonl", size = 1024, type = "application/jsonl") {
  const file = new File([new Uint8Array(size)], name, { type });
  return file;
}

beforeEach(() => {
  authStorage.clear();
  authStorage.setToken({ accessToken: "tok", tokenType: "bearer", expiresAt: Date.now() + 60_000 });
  authStorage.setUser({ id: "u-1", email: "ada@example.com", username: "ada", role: "user" });
  apiMock.get.mockReset();
  (uploadFile as unknown as { mockReset: () => void }).mockReset();
  nav.push.mockReset();
});

afterEach(() => {
  authStorage.clear();
});

describe("UploadDatasetPage", () => {
  it("shows validation errors for an empty name", async () => {
    const user = userEvent.setup();
    render(
      <TestProviders>
        <UploadDatasetPage searchParams={searchParams}/>
      </TestProviders>,
    );

    // ponytail: the page uses use(searchParams) and is wrapped in Suspense,
    // so the form is mounted after a microtask. findByTestId waits for the
    // upload zone to appear before we touch the file input.
    await screen.findByTestId("upload-zone");

    const file = makeFile();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, file);

    await user.click(screen.getByRole("button", { name: /upload dataset/i }));

    expect(await screen.findByText(/name is required/i)).toBeInTheDocument();
    expect(uploadFile).not.toHaveBeenCalled();
  });

  it("calls uploadFile and redirects on success", async () => {
    (uploadFile as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(datasetDetail);
    const user = userEvent.setup();
    render(
      <TestProviders>
        <UploadDatasetPage searchParams={searchParams}/>
      </TestProviders>,
    );

    await screen.findByTestId("upload-zone");

    const file = makeFile();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, file);

    await user.type(screen.getByLabelText(/^name$/i), "my-corpus");

    await user.click(screen.getByRole("button", { name: /upload dataset/i }));

    await waitFor(() => {
      expect(uploadFile).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(nav.push).toHaveBeenCalledWith("/datasets/ds-1");
    });
  });

  it("displays a backend error message when the upload fails", async () => {
    (uploadFile as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(
      new ApiError("VALIDATION_FAILED", "Schema mismatch", 422),
    );
    const user = userEvent.setup();
    render(
      <TestProviders>
        <UploadDatasetPage searchParams={searchParams}/>
      </TestProviders>,
    );

    await screen.findByTestId("upload-zone");

    const file = makeFile();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, file);
    await user.type(screen.getByLabelText(/^name$/i), "broken");

    await user.click(screen.getByRole("button", { name: /upload dataset/i }));

    expect(await screen.findByText(/schema mismatch/i)).toBeInTheDocument();
    expect(nav.push).not.toHaveBeenCalled();
  });

  it("displays a network error message when the upload throws a non-Api error", async () => {
    (uploadFile as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new TypeError("NetworkError"));
    const user = userEvent.setup();
    render(
      <TestProviders>
        <UploadDatasetPage searchParams={searchParams}/>
      </TestProviders>,
    );

    await screen.findByTestId("upload-zone");

    const file = makeFile();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, file);
    await user.type(screen.getByLabelText(/^name$/i), "my-corpus");

    await user.click(screen.getByRole("button", { name: /upload dataset/i }));

    expect(await screen.findByText(/network error/i)).toBeInTheDocument();
  });

  it("rejects an unsupported file extension via the dropzone", async () => {
    render(
      <TestProviders>
        <UploadDatasetPage searchParams={searchParams}/>
      </TestProviders>,
    );

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const bad = new File([new Uint8Array(10)], "notes.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [bad] } });

    expect(await screen.findByText(/unsupported file type/i)).toBeInTheDocument();
    expect(uploadFile).not.toHaveBeenCalled();
  });

  it("accepts a drop event with a valid file", async () => {
    (uploadFile as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(datasetDetail);
    render(
      <TestProviders>
        <UploadDatasetPage searchParams={searchParams}/>
      </TestProviders>,
    );

    const zone = await screen.findByTestId("upload-zone");
    const file = makeFile();
    fireEvent.drop(zone, { dataTransfer: { files: [file] } });

    await waitFor(() => {
      expect(screen.getAllByText(/corpus\.jsonl/i).length).toBeGreaterThan(0);
    });
  });
});
