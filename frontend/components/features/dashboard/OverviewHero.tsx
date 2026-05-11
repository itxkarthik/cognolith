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
  { title: "Upload", href: "/dashboard/documents", icon: Upload, tone: "teal" },
  { title: "Chat", href: "/dashboard/chat", icon: MessageSquare, tone: "lime" },
  { title: "Search", href: "/dashboard/search", icon: Search, tone: "amber" },
];

const toneClass: Record<string, string> = {
  cyan: "border-cyan-400/30 bg-cyan-500/6 text-cyan-200 hover:border-cyan-300/60",
  teal: "border-teal-400/30 bg-teal-500/6 text-teal-200 hover:border-teal-300/60",
  lime: "border-lime-400/28 bg-lime-500/6 text-lime-200 hover:border-lime-300/60",
  amber: "border-amber-400/28 bg-amber-500/6 text-amber-200 hover:border-amber-300/60",
};

export function OverviewHero() {
  return (
    <Card className="relative overflow-hidden border-cyan-500/20 bg-[#01040f]/96 shadow-[0_0_42px_rgba(0,255,255,0.06)]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18%_14%,rgba(0,255,255,0.07),transparent_40%),radial-gradient(circle_at_84%_16%,rgba(20,184,166,0.09),transparent_34%)]" />
      <CardHeader className="relative gap-4 border-b border-cyan-500/20 px-8 py-8">
        <div className="flex items-center gap-3">
          <Badge className="rounded-full border border-cyan-400/40 bg-cyan-500/15 text-cyan-200">Overview</Badge>
          <Badge variant="outline" className="rounded-full border-teal-400/35 bg-teal-500/10 text-teal-200">Realtime</Badge>
        </div>
        <div className="max-w-3xl space-y-3">
          <CardTitle className="text-5xl font-black tracking-tight text-transparent bg-clip-text bg-[linear-gradient(110deg,#9ae8ff_18%,#b9f6ff_48%,#9ae8ff_80%)] sm:text-6xl">
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
              transition={{ delay: idx * 0.05, duration: 0.36, ease: [0.22, 1, 0.36, 1] }}
              className="rounded-2xl border border-cyan-400/25 bg-cyan-500/7 p-5"
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
                transition={{ delay: 0.12 + idx * 0.05, duration: 0.38, ease: [0.22, 1, 0.36, 1] }}
              >
                <Link href={action.href} className={`group block rounded-2xl border p-5 transition-all duration-400 ${toneClass[action.tone]}`}>
                  <div className="flex min-h-[122px] items-center gap-4">
                    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-current/40 bg-black/30">
                      <Icon className="h-5 w-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-2">
                        <h3 className="text-2xl ml-2 font-semibold tracking-tight">{action.title}</h3>
                        <ArrowUpRight className="mt-1 h-5 w-5 shrink-0 opacity-55 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
                      </div>
                    </div>
                  </div>
                </Link>
              </motion.div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
