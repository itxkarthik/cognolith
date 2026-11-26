"use client";

import { useTheme } from "next-themes";
import { CheckCircle2, MailWarning, MoonStar, Monitor, ShieldCheck, Sparkles, SunMedium, UserCircle2 } from "lucide-react";

import { useAuth } from "@/lib/hooks/useAuth";
import { AIModelSettings } from "@/components/features/settings/AIModelSettings";
import { EmailChangeForm } from "@/components/features/settings/EmailChangeForm";
import { GoogleDriveBackupSettings } from "@/components/features/settings/GoogleDriveBackupSettings";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from "@/components/ui";

export default function SettingsPage() {
  const { user } = useAuth();
  const { theme, setTheme, resolvedTheme } = useTheme();
  const currentTheme = theme === "system" ? resolvedTheme : theme;

  return (
    <div className="space-y-6">
      <section className="space-y-2">
        <Badge variant="outline">Profile and settings</Badge>
        <h1 className="text-2xl font-bold text-foreground">Account preferences</h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Keep your profile, theme, and workspace behavior aligned with how you work.
        </p>
      </section>

      <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
        <Card className="border-border bg-card">
          <CardHeader className="border-b border-border">
            <CardTitle>Profile</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 py-5">
            <div className="flex items-start gap-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-sm border border-border bg-muted">
                <UserCircle2 className="h-6 w-6 text-muted-foreground" />
              </div>
              <div className="min-w-0">
                <p className="font-semibold text-foreground">{user?.full_name ?? "User"}</p>
                <p className="text-sm text-muted-foreground">{user?.email ?? "No email on file"}</p>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground">Workspace name</p>
                <div className="border border-border bg-muted px-3 py-2 text-sm text-foreground">Cognolith</div>
              </div>
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground">Account status</p>
                <div className="flex items-center gap-2 border border-border bg-muted px-3 py-2 text-sm text-foreground">
                  {user?.is_verified ? <CheckCircle2 className="h-4 w-4" /> : <MailWarning className="h-4 w-4" />}
                  {user?.is_verified ? "Email verified" : "Verification required"}
                </div>
              </div>
            </div>

            <EmailChangeForm />
          </CardContent>
        </Card>

        <Card className="border-border bg-card">
          <CardHeader className="border-b border-border">
            <CardTitle>Appearance</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 py-5">
            <p className="text-sm text-muted-foreground">Choose the display mode that fits your environment.</p>
            <div className="grid grid-cols-3 gap-2">
              <Button
                variant={currentTheme === "light" ? "default" : "outline"}
                className="justify-center"
                onClick={() => setTheme("light")}
              >
                <SunMedium className="h-4 w-4" />
                Light
              </Button>
              <Button
                variant={currentTheme === "dark" ? "default" : "outline"}
                className="justify-center"
                onClick={() => setTheme("dark")}
              >
                <MoonStar className="h-4 w-4" />
                Dark
              </Button>
              <Button
                variant={theme === "system" ? "default" : "outline"}
                className="justify-center"
                onClick={() => setTheme("system")}
              >
                <Monitor className="h-4 w-4" />
                System
              </Button>
            </div>
            <div className="border border-border bg-muted px-3 py-2 text-sm text-muted-foreground">
              Current theme: {theme === "system" ? `system (${currentTheme ?? "light"})` : currentTheme ?? "light"}
            </div>
          </CardContent>
        </Card>
      </div>

      <AIModelSettings />

      <GoogleDriveBackupSettings />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="border-border bg-card">
          <CardHeader className="border-b border-border">
            <CardTitle>Workspace behavior</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 py-5">
            <div className="flex items-center gap-3 border border-border bg-muted px-3 py-3">
              <Sparkles className="h-4 w-4 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium text-foreground">Keep context visible</p>
                <p className="text-xs text-muted-foreground">The dashboard keeps documents, notes, and chat together.</p>
              </div>
            </div>
            <div className="flex items-center gap-3 border border-border bg-muted px-3 py-3">
              <ShieldCheck className="h-4 w-4 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium text-foreground">Protected session</p>
                <p className="text-xs text-muted-foreground">Logout and route guards keep the workspace private.</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border bg-card">
          <CardHeader className="border-b border-border">
            <CardTitle>Support</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 py-5">
            <p className="text-sm text-muted-foreground">
              Need help with sync, authentication, or document processing?
            </p>
            <Button asChild variant="outline" className="w-full justify-center">
              <a href="/dashboard/support">Open support page</a>
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
