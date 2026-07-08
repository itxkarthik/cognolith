"use client";

import type { ReactNode } from "react";
import { useEffect, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";

import { Header } from "@/components/layout/Header";
import { MobileNavigation } from "@/components/layout/MobileNavigation";
import { Sidebar } from "@/components/layout/Sidebar";
import { ErrorBoundary } from "@/components/shared/ErrorBoundary";
import { useAuthStore } from "@/store/authStore";
import { cn } from "@/lib/utils/cn";

interface DashboardLayoutProps {
  children: ReactNode;
}

const SIDEBAR_EVENT = "cognolith-sidebar-change";
const SIDEBAR_STORAGE_KEY = "cognolith-sidebar-expanded";
const LEGACY_SIDEBAR_STORAGE_KEY = "pka-sidebar-expanded";

function subscribeToSidebar(callback: () => void) {
  window.addEventListener("storage", callback);
  window.addEventListener(SIDEBAR_EVENT, callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener(SIDEBAR_EVENT, callback);
  };
}

function getSidebarSnapshot() {
  const storedValue =
    window.localStorage.getItem(SIDEBAR_STORAGE_KEY) ??
    window.localStorage.getItem(LEGACY_SIDEBAR_STORAGE_KEY);
  return storedValue !== "false";
}

export function DashboardLayout({ children }: DashboardLayoutProps) {
  const router = useRouter();
  const { isAuthenticated, hasHydrated } = useAuthStore();
  const isSidebarExpanded = useSyncExternalStore(subscribeToSidebar, getSidebarSnapshot, () => true);

  const toggleSidebar = () => {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(!isSidebarExpanded));
    window.localStorage.removeItem(LEGACY_SIDEBAR_STORAGE_KEY);
    window.dispatchEvent(new Event(SIDEBAR_EVENT));
  };

  useEffect(() => {
    if (hasHydrated && !isAuthenticated) {
      router.push("/auth/login");
    }
  }, [hasHydrated, isAuthenticated, router]);

  if (!hasHydrated) {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center bg-background text-foreground">
        <div className="border border-border bg-muted px-4 py-3 text-center">
          <p className="text-sm text-muted-foreground">Verifying authentication...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return (
    <ErrorBoundary>
      <div className="min-h-[100dvh] w-full bg-background text-foreground">
        <Sidebar expanded={isSidebarExpanded} onToggle={toggleSidebar} />
        <Header sidebarExpanded={isSidebarExpanded} />
        <MobileNavigation />
        <main
          className={cn(
            "px-4 pb-[calc(5rem+env(safe-area-inset-bottom))] pt-[4.5rem] transition-[margin] duration-200 lg:px-6 lg:pb-8 lg:pt-20",
            isSidebarExpanded ? "lg:ml-64" : "lg:ml-16"
          )}
        >
          {children}
        </main>
      </div>
    </ErrorBoundary>
  );
}
