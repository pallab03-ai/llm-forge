"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { fetchCurrentUser, loginRequest, registerRequest } from "@/features/auth/api";
import { ApiError, setUnauthorizedHandler } from "@/services/api-client";
import { authStorage } from "@/services/auth-storage";
import type { AuthToken, AuthUser } from "@/types/auth";

type AuthContextValue = {
  user: AuthUser | null;
  token: AuthToken | null;
  isAuthenticated: boolean;
  isHydrated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (payload: { email: string; username: string; password: string }) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<AuthToken | null>(null);
  const [isHydrated, setIsHydrated] = useState(false);

  useEffect(() => {
    const storedToken = authStorage.getToken();
    const storedUser = authStorage.getUser();
    setToken(storedToken);
    setUser(storedUser);
    setIsHydrated(true);

    // ponytail: best-effort session restore. If the persisted token is rejected
    // (expired, revoked, or backend was redeployed), /me 401s and the
    // unauthorized handler clears the session.
    if (storedToken) {
      fetchCurrentUser()
        .then((fresh) => {
          setUser(fresh);
          authStorage.setUser(fresh);
        })
        .catch((error) => {
          if (error instanceof ApiError && error.status === 401) {
            authStorage.clear();
            setToken(null);
            setUser(null);
          }
        });
    }
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      authStorage.clear();
      setToken(null);
      setUser(null);
    });
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const { token: nextToken, user: nextUser } = await loginRequest(email, password);
    authStorage.setToken(nextToken);
    authStorage.setUser(nextUser);
    setToken(nextToken);
    setUser(nextUser);
  }, []);

  const register = useCallback(
    async (payload: { email: string; username: string; password: string }) => {
      const { token: nextToken, user: nextUser } = await registerRequest(payload);
      authStorage.setToken(nextToken);
      authStorage.setUser(nextUser);
      setToken(nextToken);
      setUser(nextUser);
    },
    [],
  );

  const logout = useCallback(() => {
    authStorage.clear();
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      token,
      isAuthenticated: token !== null && user !== null,
      isHydrated,
      login,
      register,
      logout,
    }),
    [user, token, isHydrated, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuthContext(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuthContext must be used inside AuthProvider");
  }
  return ctx;
}
