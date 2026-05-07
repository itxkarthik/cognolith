"use client";

import Link from "next/link";
import { motion } from "motion/react";
import { ArrowUpRight, FileText, MessageSquare, Search, Upload } from "lucide-react";

import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle, Separator } from "@/components/ui";

const stats = [
  { label: "Total Notes", value: "00" },
  { label: "Documents", value: "00" },
  { label: "Sessions", value: "00" },
];

const actions = [
  { title: "New Note", href: "/dashboard/notes", icon: FileText, tone: "cyan" },
  { title: "Upload", href: "/dashboard/documents", icon: Upload, tone: "pink" },
  { title: "Chat", href: "/dashboard/chat", icon: MessageSquare, tone: "lime" },
  { title: "Search", href: "/dashboard/search", icon: Search, tone: "amber" },
];

const toneClass: Record<string, string> = {
  cyan: "border-cyan-400/35 bg-cyan-500/10 text-cyan-200 hover:border-cyan-300/60",
  pink: "border-fuchsia-400/35 bg-fuchsia-500/10 text-fuchsia-200 hover:border-fuchsia-300/60",
  lime: "border-lime-400/35 bg-lime-500/10 text-lime-200 hover:border-lime-300/60",
  amber: "border-amber-400/35 bg-amber-500/10 text-amber-200 hover:border-amber-300/60",
};

export function OverviewHero() {
  return (
    <Card className="relative overflow-hidden border-cyan-500/30 bg-[#070b1d]/85 shadow-[0_0_50px_rgba(0,255,255,0.12)]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_15%,rgba(0,255,255,0.12),transparent_40%),radial-gradient(circle_at_85%_10%,rgba(217,70,239,0.16),transparent_36%)]" />
      <CardHeader className="relative gap-4 border-b border-cyan-500/20 px-8 py-8">
        <div className="flex items-center gap-3">
          <Badge className="rounded-full border border-cyan-400/40 bg-cyan-500/15 text-cyan-200">Overview</Badge>
          <Badge variant="outline" className="rounded-full border-fuchsia-400/35 bg-fuchsia-500/10 text-fuchsia-200">Realtime</Badge>
        </div>
        <div className="max-w-3xl space-y-3">
          <CardTitle className="text-4xl font-black tracking-tight text-transparent bg-clip-text bg-[linear-gradient(110deg,#8be9ff_20%,#f0abfc_48%,#8be9ff_80%)] sm:text-5xl">
            Command Your Knowledge Grid
          </CardTitle>
          <CardDescription className="text-base text-cyan-100/70 sm:text-lg">
            Notes, documents, and AI context layered in a single neon workspace built for focus.
          </CardDescription>
        </div>
      </CardHeader>

      <CardContent className="relative space-y-8 px-8 py-8">
        <div className="grid gap-4 sm:grid-cols-3">
          {stats.map((item, idx) => (
            <motion.div
              key={item.label}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.06, duration: 0.3 }}
              className="rounded-2xl border border-cyan-400/30 bg-cyan-500/10 p-5"
            >
              <p className="text-[11px] uppercase tracking-[0.2em] text-cyan-200/70">{item.label}</p>
              <p className="mt-3 text-4xl font-black tracking-tight text-cyan-100">{item.value}</p>
            </motion.div>
          ))}
        </div>

        <Separator className="bg-cyan-500/20" />

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {actions.map((action, idx) => {
            const Icon = action.icon;
            return (
              <motion.div
                key={action.title}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 + idx * 0.07, duration: 0.32 }}
              >
                <Link
                  href={action.href}
                  className={`group block rounded-2xl border p-5 transition-all duration-300 ${toneClass[action.tone]}`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-current/40 bg-black/25">
                      <Icon className="h-5 w-5" />
                    </div>
                    <ArrowUpRight className="h-5 w-5 opacity-55 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
                  </div>
                  <h3 className="mt-5 text-base font-semibold">{action.title}</h3>
                </Link>
              </motion.div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
