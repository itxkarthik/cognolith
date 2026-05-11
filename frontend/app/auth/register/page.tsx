"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { motion } from "motion/react";

import { Button, Card, CardContent, Input, Label } from "@/components/ui";
import { register } from "@/lib/api/auth";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { useAuthStore } from "@/store/authStore";

export default function RegisterPage() {
  const router = useRouter();
  const { isAuthenticated, hasHydrated } = useAuthStore();
  const [fullName, setFullName] = useState("");
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
      await register({ full_name: fullName, email, password });
      router.push("/auth/login");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to register.");
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
            <p className="text-xs uppercase tracking-[0.2em] text-cyan-200/70">Get Started</p>
            <h1 className="mt-2 text-3xl font-bold text-cyan-50">Create account</h1>
            <p className="mt-1 text-sm text-cyan-100/65">Build your personal knowledge system.</p>

            <form onSubmit={onSubmit} className="mt-6 space-y-5">
              <div className="space-y-2">
                <Label className="text-cyan-100/85">Full name</Label>
                <Input value={fullName} onChange={(event) => setFullName(event.target.value)} type="text" required className="border-cyan-500/30 bg-cyan-500/5 text-cyan-50" placeholder="Karthik" />
              </div>
              <div className="space-y-2">
                <Label className="text-cyan-100/85">Email</Label>
                <Input value={email} onChange={(event) => setEmail(event.target.value)} type="email" required className="border-cyan-500/30 bg-cyan-500/5 text-cyan-50" placeholder="you@example.com" />
              </div>
              <div className="space-y-2">
                <Label className="text-cyan-100/85">Password</Label>
                <Input value={password} onChange={(event) => setPassword(event.target.value)} type="password" minLength={8} required className="border-cyan-500/30 bg-cyan-500/5 text-cyan-50" placeholder="At least 8 characters" />
              </div>
              {error ? <div className="rounded-lg border border-rose-500/35 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</div> : null}
              <Button type="submit" disabled={isSubmitting} className="w-full bg-cyan-300 text-slate-900 hover:bg-cyan-200">
                {isSubmitting ? <LoadingSpinner className="text-slate-900" /> : "Create account"}
              </Button>
            </form>

            <p className="mt-6 text-center text-sm text-cyan-100/65">
              Already have an account?{" "}
              <Link href="/auth/login" className="font-semibold text-teal-300 hover:text-teal-200">
                Sign in
              </Link>
            </p>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  );
}
