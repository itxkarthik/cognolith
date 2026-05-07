"use client";

import Link from "next/link";
import { motion } from "motion/react";
import { OverviewHero } from "@/components/features/dashboard/OverviewHero";
import { StatusTerminal } from "@/components/features/dashboard/StatusTerminal";
import { ArrowUpRight, FileText, MessageSquare, Search, Upload } from "lucide-react";

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Separator,
} from "@/components/ui";

export default function DashboardPage() {
  const quickActions = [
    {
      title: "New Note",
      href: "/dashboard/notes",
      icon: FileText,
      description: "Create a new note",
    },
    {
      title: "Upload Document",
      href: "/dashboard/documents",
      icon: Upload,
      description: "Add a document",
    },
    {
      title: "Start Chat",
      href: "/dashboard/chat",
      icon: MessageSquare,
      description: "Talk with Ether",
    },
    {
      title: "Search Knowledge",
      href: "/dashboard/search",
      icon: Search,
      description: "Query knowledgebase",
    },
  ];

  return (
    <div className="space-y-8 max-w-7xl">
      <StatusTerminal />

      <OverviewHero />

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {quickActions.map((action, idx) => {
          const IconComponent = action.icon;
          return (
            <motion.div
              key={action.title}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.12 + idx * 0.05, duration: 0.28 }}
            >
            <Card className="group border-cyan-500/25 bg-[#070b1d]/85 transition hover:border-cyan-300/45 hover:shadow-[0_0_24px_rgba(0,255,255,0.15)]">
              <CardContent className="flex h-full flex-col gap-4 p-5">
                <div className="flex items-start justify-between">
                  <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-cyan-400/35 bg-cyan-500/15 text-cyan-200 transition group-hover:border-cyan-300/70">
                    <IconComponent className="h-5 w-5" />
                  </div>
                  <ArrowUpRight className="h-5 w-5 text-cyan-100/40 transition group-hover:text-cyan-100" />
                </div>

                <div className="space-y-1">
                  <h2 className="text-base font-semibold text-cyan-50">{action.title}</h2>
                  <p className="text-sm text-cyan-100/65">{action.description}</p>
                </div>

                <div className="mt-auto flex items-center justify-between pt-2">
                  <Badge variant="outline" className="border-cyan-400/30 bg-cyan-500/10 text-cyan-100/70">
                    Quick action
                  </Badge>
                  <Button asChild variant="ghost" size="sm" className="h-8 rounded-full px-3 text-cyan-100/70 hover:bg-cyan-500/15 hover:text-cyan-100">
                    <Link href={action.href}>Open</Link>
                  </Button>
                </div>
              </CardContent>
            </Card>
            </motion.div>
          );
        })}
      </section>

      <Card className="border-cyan-500/25 bg-[#070b1d]/85">
        <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0 pb-4">
          <div>
            <Badge variant="secondary" className="rounded-full bg-cyan-500/15 text-cyan-100/75">
              Recent activity
            </Badge>
            <CardTitle className="mt-3 text-lg text-cyan-50">Latest updates</CardTitle>
            <CardDescription className="mt-1 text-cyan-100/65">
              Your workspace is quiet for now. Start by creating a note or uploading a document.
            </CardDescription>
          </div>
          <Button variant="ghost" size="sm" className="rounded-full text-cyan-100/70 hover:bg-cyan-500/15 hover:text-cyan-100" asChild>
            <Link href="/dashboard/search">View all</Link>
          </Button>
        </CardHeader>

        <Separator className="bg-cyan-500/20" />

        <CardContent className="py-6">
          <div className="grid gap-4 md:grid-cols-3">
            {[
              {
                title: "Notes",
                description: "Capture an idea, summary, or reference point.",
                cta: "Create note",
                href: "/dashboard/notes",
              },
              {
                title: "Documents",
                description: "Bring PDFs, docs, and screenshots into the vault.",
                cta: "Upload file",
                href: "/dashboard/documents",
              },
              {
                title: "Chat",
                description: "Ask questions and keep the conversation attached to context.",
                cta: "Open chat",
                href: "/dashboard/chat",
              },
            ].map((item) => (
              <div key={item.title} className="rounded-2xl border border-cyan-500/20 bg-cyan-500/[0.05] p-4">
                <p className="text-sm font-semibold text-cyan-100">{item.title}</p>
                <p className="mt-2 text-sm text-cyan-100/65">{item.description}</p>
                <Button asChild variant="link" className="mt-4 h-auto p-0 text-cyan-300 hover:text-cyan-100">
                  <Link href={item.href}>{item.cta}</Link>
                </Button>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
