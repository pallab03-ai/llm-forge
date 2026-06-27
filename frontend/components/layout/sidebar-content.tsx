"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import {
  Activity,
  BarChart3,
  Database,
  FlaskConical,
  LayoutDashboard,
  Rocket,
  Settings as SettingsIcon,
  Sparkles,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

type NavItem = {
  label: string;
  href: string;
  icon: LucideIcon;
};

const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Datasets", href: "/datasets", icon: Database },
  { label: "Training", href: "/training", icon: Sparkles },
  { label: "Evaluations", href: "/evaluations", icon: FlaskConical },
  { label: "Models", href: "/models", icon: BarChart3 },
  { label: "Deployments", href: "/deployments", icon: Rocket },
  { label: "Monitoring", href: "/monitoring", icon: Activity },
  { label: "Settings", href: "/settings", icon: SettingsIcon },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/dashboard") return pathname === "/dashboard";
  return pathname === href || pathname.startsWith(`${href}/`);
}

type SidebarContentProps = {
  onNavigate?: () => void;
};

export function SidebarContent({ onNavigate }: SidebarContentProps) {
  const pathname = usePathname() ?? "";

  return (
    <div className="flex h-full flex-col gap-2">
      <div className="flex h-14 items-center gap-2 border-b px-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <Sparkles className="h-4 w-4" />
        </div>
        <div className="flex flex-col leading-tight">
          <span className="text-sm font-semibold">LLM Forge</span>
          <span className="text-xs text-muted-foreground">LLMOps</span>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-2 py-3">
        {NAV_ITEMS.map((item) => {
          const active = isActive(pathname, item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-secondary text-secondary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="border-t p-3 text-xs text-muted-foreground">
        <p>Phase 8.1 — Foundation</p>
      </div>
    </div>
  );
}
