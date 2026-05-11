"use client";

import type { ReactNode } from "react";
import { useEffect, useRef } from "react";
import { usePathname, useRouter } from "next/navigation";
import { motion } from "motion/react";
import gsap from "gsap";

import { Header } from "@/components/layout/Header";
import { Sidebar } from "@/components/layout/Sidebar";
import { ErrorBoundary } from "@/components/shared/ErrorBoundary";
import { useAuthStore } from "@/store/authStore";

interface DashboardLayoutProps {
  children: ReactNode;
}

export function DashboardLayout({ children }: DashboardLayoutProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { isAuthenticated, hasHydrated } = useAuthStore();
  const glowRef = useRef<HTMLDivElement>(null);
  const glowCoreRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (hasHydrated && !isAuthenticated) {
      router.push("/auth/login");
    }
  }, [hasHydrated, isAuthenticated, router]);

  useEffect(() => {
    const element = glowRef.current;
    const coreElement = glowCoreRef.current;
    if (!element || !coreElement) return;

    gsap.set([element, coreElement], { force3D: true });

    const moveX = gsap.quickTo(element, "x", { duration: 0.38, ease: "power2.out" });
    const moveY = gsap.quickTo(element, "y", { duration: 0.38, ease: "power2.out" });
    const moveCoreX = gsap.quickTo(coreElement, "x", { duration: 0.24, ease: "power2.out" });
    const moveCoreY = gsap.quickTo(coreElement, "y", { duration: 0.24, ease: "power2.out" });

    // Keep glow visible after route transitions before next mouse move.
    moveX(window.innerWidth * 0.5 - 220);
    moveY(window.innerHeight * 0.35 - 220);
    moveCoreX(window.innerWidth * 0.5 - 110);
    moveCoreY(window.innerHeight * 0.35 - 110);

    const placeAt = (x: number, y: number) => {
      moveX(x - 220);
      moveY(y - 220);
      moveCoreX(x - 110);
      moveCoreY(y - 110);
    };

    const handleMouseMove = (event: MouseEvent) => {
      placeAt(event.clientX, event.clientY);
    };

    const handlePointerMove = (event: PointerEvent) => {
      placeAt(event.clientX, event.clientY);
    };

    const resetGlow = () => {
      placeAt(window.innerWidth * 0.5, window.innerHeight * 0.35);
    };

    const handleVisibilityChange = () => {
      if (!document.hidden) {
        resetGlow();
      }
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("pointermove", handlePointerMove);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("focus", resetGlow);
    window.addEventListener("pageshow", resetGlow);

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("pointermove", handlePointerMove);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("focus", resetGlow);
      window.removeEventListener("pageshow", resetGlow);
    };
  }, [hasHydrated, isAuthenticated, pathname]);

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
        <div className="pointer-events-none absolute inset-0 cyber-grid opacity-28" />
        <div
          ref={glowRef}
          className="pointer-events-none fixed left-0 top-0 z-10 h-[460px] w-[460px] rounded-full mix-blend-screen blur-2xl"
          style={{
            background:
              "radial-gradient(circle, rgba(84, 195, 210, 0.14) 0%, rgba(40, 148, 141, 0.1) 34%, rgba(2, 6, 17, 0) 70%)",
            willChange: "transform",
          }}
        />
        <div
          ref={glowCoreRef}
          className="pointer-events-none fixed left-0 top-0 z-10 h-[240px] w-[240px] rounded-full mix-blend-screen blur-xl"
          style={{
            background:
              "radial-gradient(circle, rgba(126, 222, 233, 0.2) 0%, rgba(36, 162, 178, 0.12) 36%, rgba(2, 6, 17, 0) 72%)",
            willChange: "transform",
          }}
        />
        <div className="pointer-events-none absolute -top-40 left-1/3 h-80 w-80 rounded-full bg-cyan-500/10 blur-3xl" />
        <div className="pointer-events-none absolute bottom-0 right-10 h-96 w-96 rounded-full bg-teal-500/8 blur-3xl" />
        <Sidebar />
        <Header />
        <motion.main
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.46, ease: [0.22, 1, 0.36, 1] }}
          className="relative z-20 ml-72 px-8 pb-12 pt-24"
        >
          {children}
        </motion.main>
      </div>
    </ErrorBoundary>
  );
}
