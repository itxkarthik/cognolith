"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/authStore";

export default function Home() {
  const router = useRouter();
  const { isAuthenticated, hasHydrated } = useAuthStore();

  useEffect(() => {
    if (hasHydrated) {
      if (isAuthenticated) {
        router.push("/dashboard");
      } else {
        router.push("/auth/login");
      }
    }
  }, [hasHydrated, isAuthenticated, router]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-xl border border-border p-8 text-center">
        <p className="text-sm text-muted-foreground">Loading workspace</p>
        <h1 className="mt-3 text-xl font-bold text-foreground">Cognolith</h1>
        <p className="mt-2 text-sm text-muted-foreground">Preparing notes, documents, and AI conversations...</p>
      </div>
    </div>
  );
}
