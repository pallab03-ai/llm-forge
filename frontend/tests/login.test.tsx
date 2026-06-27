import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import LoginPage from "@/app/login/page";
import { AppProviders } from "@/providers";
import { ApiError } from "@/services/api-client";
import { authStorage } from "@/services/auth-storage";

const nav = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
  pathname: "/login",
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

describe("LoginPage", () => {
  beforeEach(() => {
    authStorage.clear();
    apiMock.post.mockReset();
    apiMock.get.mockReset();
    nav.push.mockReset();
    nav.replace.mockReset();
  });

  it("shows validation errors for empty fields", async () => {
    const user = userEvent.setup();
    render(<AppProviders><LoginPage /></AppProviders>);

    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText(/enter a valid email address/i)).toBeInTheDocument();
    expect(screen.getByText(/password is required/i)).toBeInTheDocument();
    expect(apiMock.post).not.toHaveBeenCalled();
  });

  it("rejects malformed email with a Zod error", async () => {
    const user = userEvent.setup();
    render(<AppProviders><LoginPage /></AppProviders>);

    await user.type(screen.getByLabelText(/email/i), "not-an-email");
    await user.type(screen.getByLabelText(/password/i), "secret123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText(/enter a valid email address/i)).toBeInTheDocument();
    expect(apiMock.post).not.toHaveBeenCalled();
  });

  it("calls apiClient.post with the form values on submit", async () => {
    apiMock.post.mockResolvedValueOnce({
      access_token: "tok",
      token_type: "bearer",
      expires_in: 3600,
      user: { id: "u-1", email: "ada@example.com", username: "ada", role: "user" },
    });

    const user = userEvent.setup();
    render(<AppProviders><LoginPage /></AppProviders>);

    await user.type(screen.getByLabelText(/email/i), "ada@example.com");
    await user.type(screen.getByLabelText(/password/i), "secret123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(apiMock.post).toHaveBeenCalledWith("/auth/login", {
        email: "ada@example.com",
        password: "secret123",
      });
    });

    expect(authStorage.getToken()?.accessToken).toBe("tok");
    expect(nav.push).toHaveBeenCalledWith("/dashboard");
  });

  it("displays an error message for 401 invalid credentials", async () => {
    apiMock.post.mockRejectedValueOnce(new ApiError("INVALID_CREDENTIALS", "Invalid credentials", 401));

    const user = userEvent.setup();
    render(<AppProviders><LoginPage /></AppProviders>);

    await user.type(screen.getByLabelText(/email/i), "ada@example.com");
    await user.type(screen.getByLabelText(/password/i), "wrong");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/invalid email or password/i);
    expect(nav.push).not.toHaveBeenCalled();
  });

  it("displays a network error when the request fails with a non-Api error", async () => {
    apiMock.post.mockRejectedValueOnce(new TypeError("NetworkError"));

    const user = userEvent.setup();
    render(<AppProviders><LoginPage /></AppProviders>);

    await user.type(screen.getByLabelText(/email/i), "ada@example.com");
    await user.type(screen.getByLabelText(/password/i), "secret123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/network error/i);
  });
});
