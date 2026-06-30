"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

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
    <div className="flex min-h-[100dvh] items-center justify-center bg-background px-4">
      <Card className="w-full max-w-md border-border bg-background">
        <CardContent className="p-8">
          <p className="text-xs text-muted-foreground">Welcome back</p>
          <h1 className="mt-2 text-3xl font-bold text-foreground">Sign in</h1>
          <p className="mt-1 text-sm text-muted-foreground">Access your personal knowledge workspace.</p>

          <form onSubmit={onSubmit} className="mt-6 space-y-4">
            <div className="space-y-2">
              <Label htmlFor="login-email">Email address</Label>
              <Input
                id="login-email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                type="email"
                autoComplete="email"
                required
                placeholder="name@example.com"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="login-password">Password</Label>
              <Input
                id="login-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                type="password"
                autoComplete="current-password"
                required
                placeholder="Enter your password"
              />
            </div>

            {error ? (
              <div className="rounded-sm border border-[#ff3b30] bg-[#ff3b30]/10 px-4 py-3 text-sm text-[#a50011]">
                {error}
              </div>
            ) : null}

            <Button type="submit" disabled={isSubmitting} className="w-full">
              {isSubmitting ? <LoadingSpinner /> : "Sign in"}
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-muted-foreground">
            No account yet?{" "}
            <Link href="/auth/register" className="font-medium underline underline-offset-4">
              Create one
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
