"use client";

import type { ReactNode } from "react";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion } from "motion/react";

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
      <div className="min-h-screen bg-background text-foreground flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-2 border-cyan-400/30 border-t-cyan-300 mx-auto mb-4"></div>
          <p className="text-sm text-cyan-100/70">Verifying authentication...</p>
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
      <div className="relative min-h-screen w-full overflow-hidden bg-background text-foreground">
        <div className="pointer-events-none absolute inset-0 cyber-grid opacity-40" />
        <div className="pointer-events-none absolute -top-40 left-1/3 h-80 w-80 rounded-full bg-cyan-500/20 blur-3xl" />
        <div className="pointer-events-none absolute bottom-0 right-10 h-96 w-96 rounded-full bg-fuchsia-500/15 blur-3xl" />
        <Sidebar />
        <Header />
        <motion.main
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: "easeOut" }}
          className="relative ml-72 px-8 pb-12 pt-24"
        >
          {children}
        </motion.main>
      </div>
    </ErrorBoundary>
  );
}
