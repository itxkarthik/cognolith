import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { ErrorBoundary } from "@/components/shared/ErrorBoundary";
import { OfflineIndicator } from "@/components/shared/OfflineIndicator";
import { AuthBootstrap } from "@/components/auth/AuthBootstrap";
import { Toaster } from "@/components/ui/sonner";
import "./globals.css";
import { cn } from "@/lib/utils";

const inter = Inter({subsets:['latin'],variable:'--font-sans'});

export const metadata: Metadata = {
	title: "Personal Knowledge Assistant",
	description: "Organize your notes, documents, and AI conversations in one place.",
	metadataBase: new URL(process.env.NEXT_PUBLIC_FRONTEND_URL || "http://localhost:8080"),
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={cn("font-sans", inter.variable)}>
      <body className={`${inter.variable} font-sans antialiased text-white`}>
        <AuthBootstrap />
        <OfflineIndicator />
        <Toaster />
        <ErrorBoundary>{children}</ErrorBoundary>
      </body>
    </html>
  );
}
