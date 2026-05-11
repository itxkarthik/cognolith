"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { motion } from "motion/react";

import { Button, Card, CardContent, Input, Label } from "@/components/ui";
import { getCurrentUser, login } from "@/lib/api/auth";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { useAuthStore } from "@/store/authStore";

export default function LoginPage() {
  const router = useRouter();
  const setAuth = useAuthStore((state) => state.setAuth);
  const { isAuthenticated, hasHydrated } = useAuthStore();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (hasHydrated && isAuthenticated) {
      router.push("/dashboard");
    }
  }, [hasHydrated, isAuthenticated, router]);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await login({ email, password });
      const user = await getCurrentUser();
      setAuth({ user });
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to login.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background px-4">
      <div className="pointer-events-none absolute inset-0 cyber-grid opacity-30" />
      <div className="pointer-events-none absolute -left-32 top-16 h-72 w-72 rounded-full bg-cyan-500/15 blur-3xl" />
      <div className="pointer-events-none absolute -right-32 bottom-10 h-72 w-72 rounded-full bg-teal-500/12 blur-3xl" />

      <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} className="relative w-full max-w-md">
        <Card className="border-cyan-500/25 bg-[#070b1d]/85 backdrop-blur-xl">
          <CardContent className="p-8">
            <p className="text-xs uppercase tracking-[0.2em] text-cyan-200/70">Welcome Back</p>
            <h1 className="mt-2 text-3xl font-bold text-cyan-50">Sign in</h1>
            <p className="mt-1 text-sm text-cyan-100/65">Access your knowledge workspace.</p>

            <form onSubmit={onSubmit} className="mt-6 space-y-5">
              <div className="space-y-2">
                <Label className="text-cyan-100/85">Email</Label>
                <Input value={email} onChange={(event) => setEmail(event.target.value)} type="email" required className="border-cyan-500/30 bg-cyan-500/5 text-cyan-50" placeholder="you@example.com" />
              </div>
              <div className="space-y-2">
                <Label className="text-cyan-100/85">Password</Label>
                <Input value={password} onChange={(event) => setPassword(event.target.value)} type="password" required className="border-cyan-500/30 bg-cyan-500/5 text-cyan-50" placeholder="••••••••" />
              </div>

              {error ? <div className="rounded-lg border border-rose-500/35 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</div> : null}

              <Button type="submit" disabled={isSubmitting} className="w-full bg-cyan-300 text-slate-900 hover:bg-cyan-200">
                {isSubmitting ? <LoadingSpinner className="text-slate-900" /> : "Sign in"}
              </Button>
            </form>

            <p className="mt-6 text-center text-sm text-cyan-100/65">
              No account yet?{" "}
              <Link href="/auth/register" className="font-semibold text-teal-300 hover:text-teal-200">
                Create one
              </Link>
            </p>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  );
}
