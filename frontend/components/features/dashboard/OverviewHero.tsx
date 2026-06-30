"use client";

import { FileText, MessageSquareText, NotebookPen, RefreshCw, Upload } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui";

interface OverviewHeroProps {
  userName: string;
  noteCount: number;
  documentCount: number;
  chatCount: number;
  aiReady: boolean;
  isLoading: boolean;
  onRefresh: () => void;
}

export function OverviewHero({
  userName,
  noteCount,
  documentCount,
  chatCount,
  aiReady,
  isLoading,
  onRefresh,
}: OverviewHeroProps) {
  const stats = [
    { label: "Notes", value: noteCount, icon: NotebookPen },
    { label: "Documents", value: documentCount, icon: FileText },
    { label: "Conversations", value: chatCount, icon: MessageSquareText },
  ];

  return (
    <section>
      <div className="flex flex-col gap-5 pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs text-muted-foreground">Workspace</p>
          <h1 className="mt-2 text-2xl font-bold text-foreground sm:text-3xl">
            Welcome back, {userName}.
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
            Pick up recent work or add new context to your knowledge base.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="icon"
            onClick={onRefresh}
            disabled={isLoading}
            aria-label="Refresh dashboard"
            title="Refresh dashboard"
          >
            <RefreshCw className={isLoading ? "animate-spin" : ""} />
          </Button>
          <Button asChild variant="outline">
            <Link href="/dashboard/documents/upload">
              <Upload />
              Upload
            </Link>
          </Button>
          <Button asChild>
            <Link href="/dashboard/notes?new=1">
              <NotebookPen />
              New note
            </Link>
          </Button>
        </div>
      </div>

      <div className="grid border-y border-border sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((item) => {
          const Icon = item.icon;
          return (
            <div key={item.label} className="flex items-center justify-between gap-4 border-b border-border p-4 sm:odd:border-r lg:border-b-0 lg:border-r">
              <div>
                <p className="text-xs text-muted-foreground">{item.label}</p>
                <p className="mt-1 text-2xl font-bold text-foreground">{isLoading ? "--" : item.value}</p>
              </div>
              <Icon className="h-4 w-4 text-muted-foreground" />
            </div>
          );
        })}
        <div className="flex items-center justify-between gap-4 p-4">
          <div>
            <p className="text-xs text-muted-foreground">Local AI</p>
            <p className="mt-1 text-sm font-bold text-foreground">
              {isLoading ? "Checking" : aiReady ? "Ready" : "Unavailable"}
            </p>
          </div>
          <span className="text-muted-foreground">
            {aiReady ? "[online]" : "[offline]"}
          </span>
        </div>
      </div>
    </section>
  );
}
