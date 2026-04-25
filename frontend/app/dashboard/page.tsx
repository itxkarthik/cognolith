"use client";

import { OverviewHero } from "@/components/features/dashboard/OverviewHero";
import { StatusTerminal } from "@/components/features/dashboard/StatusTerminal";
import {
  FileText,
  Upload,
  MessageSquare,
  Search,
  ArrowUpRight,
} from "lucide-react";

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

      {/* Quick Actions */}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {quickActions.map((action) => {
          const IconComponent = action.icon;
          return (
            <a
              key={action.title}
              href={action.href}
              className="group block rounded-2xl border border-[#464554]/20 bg-[#1f1f1f] p-5 backdrop-blur transition hover:border-[#bcff5f]/40 hover:bg-[#1f1f1f]"
            >
              <div className="flex items-start justify-between">
                <IconComponent className="w-6 h-6 text-[#c0c1ff]" />
                <ArrowUpRight className="w-5 h-5 text-[#908fa0] transition group-hover:text-[#c0c1ff]" />
              </div>
              <h2 className="mt-4 font-bold text-[#e2e2e2]">{action.title}</h2>
              <p className="mt-1 text-sm text-[#c7c4d7]">
                {action.description}
              </p>
            </a>
          );
        })}
      </section>

      {/* Recent Items */}
      <section className="rounded-2xl border border-[#464554]/20 bg-[#1f1f1f] p-6">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-[#908fa0]">
              Recent Activity
            </p>
            <h3 className="mt-1 text-lg font-bold text-[#e2e2e2]">
              Latest updates
            </h3>
          </div>
          <a
            href="/dashboard/search"
            className="text-sm text-[#c7c4d7] hover:text-[#c0c1ff]"
          >
            View all
          </a>
        </div>

        <div className="space-y-3">
          <p className="rounded-xl border border-[#464554]/20 p-3 text-sm text-[#c7c4d7]">
            No activity yet. Create your first note or upload a document to get
            started.
          </p>
        </div>
      </section>
    </div>
  );
}
