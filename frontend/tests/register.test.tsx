import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import RegisterPage from "@/app/register/page";
import { AppProviders } from "@/providers";
import { ApiError } from "@/services/api-client";
import { authStorage } from "@/services/auth-storage";

const nav = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
  pathname: "/register",
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: nav.push, replace: nav.replace, refresh: vi.fn(), back: vi.fn(), forward: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => nav.pathname,
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}));

const apiMock = vi.hoisted(() => ({
  post: vi.fn(),
  get: vi.fn(),
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
    setUnauthorizedHandler: vi.fn(),
  };
});

describe("RegisterPage", () => {
  beforeEach(() => {
    authStorage.clear();
    apiMock.post.mockReset();
    apiMock.get.mockReset();
    nav.push.mockReset();
    nav.replace.mockReset();
  });

  it("rejects mismatched passwords with a confirm-password error", async () => {
    const user = userEvent.setup();
    render(<AppProviders><RegisterPage /></AppProviders>);

    await user.type(screen.getByLabelText(/username/i), "ada");
    await user.type(screen.getByLabelText(/email/i), "ada@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "password123");
    await user.type(screen.getByLabelText(/confirm password/i), "different");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText(/passwords do not match/i)).toBeInTheDocument();
    expect(apiMock.post).not.toHaveBeenCalled();
  });

  it("rejects passwords shorter than the backend minimum", async () => {
    const user = userEvent.setup();
    render(<AppProviders><RegisterPage /></AppProviders>);

    await user.type(screen.getByLabelText(/username/i), "ada");
    await user.type(screen.getByLabelText(/email/i), "ada@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "short");
    await user.type(screen.getByLabelText(/confirm password/i), "short");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText(/at least 8 characters/i)).toBeInTheDocument();
    expect(apiMock.post).not.toHaveBeenCalled();
  });

  it("rejects invalid usernames", async () => {
    const user = userEvent.setup();
    render(<AppProviders><RegisterPage /></AppProviders>);

    await user.type(screen.getByLabelText(/username/i), "ada@bad");
    await user.type(screen.getByLabelText(/email/i), "ada@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "password123");
    await user.type(screen.getByLabelText(/confirm password/i), "password123");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText(/letters, digits/i)).toBeInTheDocument();
    expect(apiMock.post).not.toHaveBeenCalled();
  });

  it("submits valid data and redirects on success", async () => {
    apiMock.post.mockResolvedValueOnce({
      access_token: "tok",
      token_type: "bearer",
      expires_in: 3600,
      user: { id: "u-1", email: "ada@example.com", username: "ada", role: "user" },
    });

    const user = userEvent.setup();
    render(<AppProviders><RegisterPage /></AppProviders>);

    await user.type(screen.getByLabelText(/username/i), "ada");
    await user.type(screen.getByLabelText(/email/i), "ada@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "password123");
    await user.type(screen.getByLabelText(/confirm password/i), "password123");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => {
      expect(apiMock.post).toHaveBeenCalledWith("/auth/register", {
        email: "ada@example.com",
        username: "ada",
        password: "password123",
      });
    });
    expect(nav.push).toHaveBeenCalledWith("/dashboard");
  });

  it("surfaces a 409 conflict on the email field", async () => {
    apiMock.post.mockRejectedValueOnce(new ApiError("USER_ALREADY_EXISTS", "Email taken", 409));

    const user = userEvent.setup();
    render(<AppProviders><RegisterPage /></AppProviders>);

    await user.type(screen.getByLabelText(/username/i), "ada");
    await user.type(screen.getByLabelText(/email/i), "ada@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "password123");
    await user.type(screen.getByLabelText(/confirm password/i), "password123");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText(/account with this email already exists/i)).toBeInTheDocument();
    expect(nav.push).not.toHaveBeenCalled();
  });
});
