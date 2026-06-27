import { apiClient } from "@/services/api-client";
import type { AuthToken, AuthUser, UserRole } from "@/types/auth";

type TokenBundle = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: {
    id: string;
    email: string;
    username: string;
    role: UserRole;
  };
};

type UserDetails = {
  id: string;
  email: string;
  username: string;
  role: UserRole;
  created_at: string;
  updated_at: string;
};

function toAuthToken(bundle: TokenBundle): AuthToken {
  return {
    accessToken: bundle.access_token,
    tokenType: "bearer",
    expiresAt: Date.now() + bundle.expires_in * 1000,
  };
}

function toAuthUser(user: TokenBundle["user"]): AuthUser {
  return {
    id: user.id,
    email: user.email,
    username: user.username,
    role: user.role,
  };
}

export async function loginRequest(email: string, password: string): Promise<{ token: AuthToken; user: AuthUser }> {
  const bundle = await apiClient.post<TokenBundle>("/auth/login", { email, password });
  return { token: toAuthToken(bundle), user: toAuthUser(bundle.user) };
}

export async function registerRequest(payload: {
  email: string;
  username: string;
  password: string;
}): Promise<{ token: AuthToken; user: AuthUser }> {
  const bundle = await apiClient.post<TokenBundle>("/auth/register", payload);
  return { token: toAuthToken(bundle), user: toAuthUser(bundle.user) };
}

export async function fetchCurrentUser(): Promise<AuthUser> {
  const details = await apiClient.get<UserDetails>("/auth/me");
  return {
    id: details.id,
    email: details.email,
    username: details.username,
    role: details.role,
  };
}
