"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

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
    <div className="flex min-h-[100dvh] items-center justify-center bg-background px-4">
      <Card className="w-full max-w-md border-border bg-background">
        <CardContent className="p-8">
          <p className="text-xs text-muted-foreground">Get started</p>
          <h1 className="mt-2 text-3xl font-bold text-foreground">Create account</h1>
          <p className="mt-1 text-sm text-muted-foreground">Build your personal knowledge system.</p>

          <form onSubmit={onSubmit} className="mt-6 space-y-4">
            <div className="space-y-2">
              <Label htmlFor="register-name">Full name</Label>
              <Input id="register-name" value={fullName} onChange={(event) => setFullName(event.target.value)} type="text" autoComplete="name" required placeholder="Enter your full name" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="register-email">Email address</Label>
              <Input id="register-email" value={email} onChange={(event) => setEmail(event.target.value)} type="email" autoComplete="email" required placeholder="name@example.com" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="register-password">Password</Label>
              <Input id="register-password" value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="new-password" minLength={8} required placeholder="Minimum 8 characters" />
            </div>

            {error ? (
              <div className="rounded-sm border border-[#ff3b30] bg-[#ff3b30]/10 px-4 py-3 text-sm text-[#a50011]">
                {error}
              </div>
            ) : null}

            <Button type="submit" disabled={isSubmitting} className="w-full">
              {isSubmitting ? <LoadingSpinner /> : "Create account"}
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-muted-foreground">
            Already have an account?{" "}
            <Link href="/auth/login" className="font-medium underline underline-offset-4">
              Sign in
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
