import type { AuthToken, AuthUser } from "@/types/auth";

const TOKEN_KEY = "llm-forge:auth-token";
const USER_KEY = "llm-forge:auth-user";

function isBrowser(): boolean {
  return typeof window !== "undefined";
}

export const authStorage = {
  getToken(): AuthToken | null {
    if (!isBrowser()) return null;
    const raw = window.localStorage.getItem(TOKEN_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as AuthToken;
    } catch {
      return null;
    }
  },

  setToken(token: AuthToken): void {
    if (!isBrowser()) return;
    window.localStorage.setItem(TOKEN_KEY, JSON.stringify(token));
  },

  clearToken(): void {
    if (!isBrowser()) return;
    window.localStorage.removeItem(TOKEN_KEY);
  },

  getUser(): AuthUser | null {
    if (!isBrowser()) return null;
    const raw = window.localStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as AuthUser;
    } catch {
      return null;
    }
  },

  setUser(user: AuthUser): void {
    if (!isBrowser()) return;
    window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  },

  clearUser(): void {
    if (!isBrowser()) return;
    window.localStorage.removeItem(USER_KEY);
  },

  clear(): void {
    authStorage.clearToken();
    authStorage.clearUser();
  },
};
