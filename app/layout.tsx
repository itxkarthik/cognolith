import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { ErrorBoundary } from "@/components/shared/ErrorBoundary";
import { AuthBootstrap } from "@/components/auth/AuthBootstrap";
import "./globals.css";

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
});

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
    <html lang="en">
      <body className={`${inter.variable} font-sans antialiased text-white`}>
        <AuthBootstrap />
        <ErrorBoundary>{children}</ErrorBoundary>
      </body>
    </html>
  );
}
