"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/hooks/use-auth";
import { Spinner } from "@/components/ui/spinner";

type ProtectedRouteProps = {
  children: React.ReactNode;
  redirectTo?: string;
};

export function ProtectedRoute({ children, redirectTo = "/login" }: ProtectedRouteProps) {
  const router = useRouter();
  const { isAuthenticated, isHydrated } = useAuth();

  useEffect(() => {
    if (isHydrated && !isAuthenticated) {
      router.replace(redirectTo);
    }
  }, [isAuthenticated, isHydrated, redirectTo, router]);

  if (!isHydrated) {
    return (
      <div className="flex h-[50vh] items-center justify-center">
        <Spinner label="Loading session" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="flex h-[50vh] items-center justify-center">
        <Spinner label="Redirecting" />
      </div>
    );
  }

  return <>{children}</>;
}
