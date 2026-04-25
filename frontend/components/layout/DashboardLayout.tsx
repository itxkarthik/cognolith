"use client";

import type { ReactNode } from "react";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { Header } from "@/components/layout/Header";
import { Sidebar } from "@/components/layout/Sidebar";
import { ErrorBoundary } from "@/components/shared/ErrorBoundary";
import { useAuthStore } from "@/store/authStore";

interface DashboardLayoutProps {
  children: ReactNode;
}

export function DashboardLayout({ children }: DashboardLayoutProps) {
  const router = useRouter();
  const { isAuthenticated, hasHydrated } = useAuthStore();

  useEffect(() => {
    if (hasHydrated && !isAuthenticated) {
      router.push("/auth/login");
    }
  }, [hasHydrated, isAuthenticated, router]);

  // Show loading state while checking authentication
  if (!hasHydrated) {
    return (
      <div className="min-h-screen bg-[#131313] text-[#e2e2e2] flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-2 border-[#c0c1ff] border-t-[#bcff5f] mx-auto mb-4"></div>
          <p className="text-sm text-[#8a8a8a]">Verifying authentication...</p>
        </div>
      </div>
    );
  }

  // Redirect will happen in useEffect, so return nothing here
  if (!isAuthenticated) {
    return null;
  }

  return (
    <ErrorBoundary>
      <div className="min-h-screen bg-[#131313] text-[#e2e2e2] w-full">
        <Sidebar />
        <Header />
        <main className="ml-64 pt-20 px-8 py-12">{children}</main>
      </div>
    </ErrorBoundary>
  );
}
