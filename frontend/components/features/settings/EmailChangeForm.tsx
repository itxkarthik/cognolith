"use client";

import { FormEvent, useState } from "react";

import { Button, Input, Label } from "@/components/ui";
import {
  cancelEmailChange,
  changeEmail,
  confirmEmailChange,
  getCurrentUser,
  resendEmailChangeCode,
} from "@/lib/api/auth";
import { sanitizeVerificationCode } from "@/lib/verification";
import { useAuthStore } from "@/store/authStore";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

/**
 * Two-step email change: request a code for the new address, then confirm it.
 * The current address keeps working until the code is confirmed. The pending
 * address comes from the signed-in user, so a reload returns to the code step.
 */
export function EmailChangeForm() {
  const pendingEmail = useAuthStore((state) => state.user?.pending_email ?? null);
  const setUser = useAuthStore((state) => state.setUser);
  const [newEmail, setNewEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const onRequestCode = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setIsSubmitting(true);
    try {
      await changeEmail(newEmail, password);
      setUser(await getCurrentUser());
      setPassword("");
    } catch (requestError) {
      setError(errorMessage(requestError, "Email address could not be changed."));
    } finally {
      setIsSubmitting(false);
    }
  };

  const onConfirm = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setIsSubmitting(true);
    try {
      setUser(await confirmEmailChange(code));
      setNewEmail("");
      setCode("");
      setNotice("Email address updated. Other devices have been signed out.");
    } catch (confirmError) {
      setError(errorMessage(confirmError, "The code could not be confirmed."));
    } finally {
      setIsSubmitting(false);
    }
  };

  const onResend = async () => {
    setError(null);
    setNotice(null);
    setIsSubmitting(true);
    try {
      await resendEmailChangeCode();
      setCode("");
      setNotice("A new code is on its way. Earlier codes no longer work.");
    } catch (resendError) {
      setError(errorMessage(resendError, "A new code could not be sent."));
    } finally {
      setIsSubmitting(false);
    }
  };

  const onCancel = async () => {
    setError(null);
    setNotice(null);
    setIsSubmitting(true);
    try {
      setUser(await cancelEmailChange());
      setCode("");
    } catch (cancelError) {
      setError(errorMessage(cancelError, "The email change could not be cancelled."));
    } finally {
      setIsSubmitting(false);
    }
  };

  if (pendingEmail) {
    return (
      <form onSubmit={onConfirm} className="space-y-3 border-t border-border pt-4">
        <div>
          <p className="text-sm font-semibold text-foreground">Confirm your new email</p>
          <p className="text-xs text-muted-foreground">
            Enter the 6-digit code sent to {pendingEmail}. Your current address stays active until
            you confirm. Codes expire after 10 minutes.
          </p>
        </div>
        <div className="space-y-1.5 sm:max-w-xs">
          <Label htmlFor="email-change-code">Verification code</Label>
          <Input
            id="email-change-code"
            inputMode="numeric"
            autoComplete="one-time-code"
            value={code}
            onChange={(event) => setCode(sanitizeVerificationCode(event.target.value))}
            required
          />
        </div>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        {notice ? <p className="text-sm text-muted-foreground">{notice}</p> : null}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" variant="outline" disabled={isSubmitting || code.length !== 6}>
            Confirm email
          </Button>
          <Button type="button" variant="ghost" onClick={onResend} disabled={isSubmitting}>
            Resend code
          </Button>
          <Button type="button" variant="ghost" onClick={onCancel} disabled={isSubmitting}>
            Cancel
          </Button>
        </div>
      </form>
    );
  }

  return (
    <form onSubmit={onRequestCode} className="space-y-3 border-t border-border pt-4">
      <div>
        <p className="text-sm font-semibold text-foreground">Change email address</p>
        <p className="text-xs text-muted-foreground">
          We&apos;ll send a code to the new address. Other devices are signed out once you confirm.
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="new-email">New email</Label>
          <Input
            id="new-email"
            type="email"
            autoComplete="email"
            value={newEmail}
            onChange={(event) => setNewEmail(event.target.value)}
            required
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="email-change-password">Current password</Label>
          <Input
            id="email-change-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </div>
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {notice ? <p className="text-sm text-muted-foreground">{notice}</p> : null}
      <Button type="submit" variant="outline" disabled={isSubmitting}>
        Send verification code
      </Button>
    </form>
  );
}
