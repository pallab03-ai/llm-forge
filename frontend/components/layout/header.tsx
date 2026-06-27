"use client";

import { LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";

export function Header() {
  const router = useRouter();
  const { user, isHydrated, logout } = useAuth();

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-3 border-b bg-card/80 px-4 backdrop-blur md:px-6">
      <div className="flex flex-1 items-center gap-2">
        <span className="text-sm font-medium text-muted-foreground">
          Foundation
        </span>
      </div>

      <div className="flex items-center gap-2">
        <ThemeToggle />
        {isHydrated ? (
          user ? (
            <div className="flex items-center gap-2">
              <span className="hidden text-sm text-muted-foreground sm:inline">
                {user.email}
              </span>
              <Button variant="ghost" size="sm" onClick={handleLogout}>
                <LogOut className="h-4 w-4" />
                <span>Logout</span>
              </Button>
            </div>
          ) : (
            <Button variant="ghost" size="sm" onClick={() => router.push("/login")}>
              <LogOut className="h-4 w-4" />
              <span>Sign in</span>
            </Button>
          )
        ) : (
          <Spinner size="sm" />
        )}
      </div>
    </header>
  );
}
