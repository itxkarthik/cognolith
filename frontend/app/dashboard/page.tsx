"use client";

import { GitBranch, Search, Settings, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import {
  OverviewHero,
  RecentChatsPanel,
  RecentDocumentsPanel,
  RecentNotesPanel,
} from "@/components/features/dashboard";
import { listChatSessions } from "@/lib/api/chat";
import { listDocuments } from "@/lib/api/documents";
import { getAIReadiness } from "@/lib/api/health";
import { listNotes } from "@/lib/api/notes";
import { useAuth } from "@/lib/hooks/useAuth";
import type { ChatResponse, DocumentResponse, NoteResponse } from "@/types";

interface DashboardData {
  notes: NoteResponse[];
  documents: DocumentResponse[];
  sessions: ChatResponse[];
  noteCount: number;
  documentCount: number;
  chatCount: number;
  aiReady: boolean;
  notesError: string | null;
  documentsError: string | null;
  chatsError: string | null;
}

const INITIAL_DATA: DashboardData = {
  notes: [],
  documents: [],
  sessions: [],
  noteCount: 0,
  documentCount: 0,
  chatCount: 0,
  aiReady: false,
  notesError: null,
  documentsError: null,
  chatsError: null,
};

function errorMessage(result: PromiseRejectedResult, fallback: string): string {
  return result.reason instanceof Error ? result.reason.message : fallback;
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [data, setData] = useState<DashboardData>(INITIAL_DATA);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshVersion, setRefreshVersion] = useState(0);

  useEffect(() => {
    let active = true;

    async function loadDashboard() {
      setIsLoading(true);
      const [notesResult, documentsResult, chatsResult, readinessResult] = await Promise.allSettled([
        listNotes({ skip: 0, limit: 4 }),
        listDocuments({ skip: 0, limit: 4 }),
        listChatSessions({ skip: 0, limit: 4 }),
        getAIReadiness(),
      ]);

      if (!active) return;

      setData({
        notes: notesResult.status === "fulfilled" ? notesResult.value.data : [],
        noteCount: notesResult.status === "fulfilled" ? notesResult.value.count : 0,
        notesError: notesResult.status === "rejected" ? errorMessage(notesResult, "Failed to load notes.") : null,
        documents: documentsResult.status === "fulfilled" ? documentsResult.value.data : [],
        documentCount: documentsResult.status === "fulfilled" ? documentsResult.value.count : 0,
        documentsError: documentsResult.status === "rejected" ? errorMessage(documentsResult, "Failed to load documents.") : null,
        sessions: chatsResult.status === "fulfilled" ? chatsResult.value.data : [],
        chatCount: chatsResult.status === "fulfilled" ? chatsResult.value.count : 0,
        chatsError: chatsResult.status === "rejected" ? errorMessage(chatsResult, "Failed to load conversations.") : null,
        aiReady: readinessResult.status === "fulfilled" && readinessResult.value.dependencies.ollama === "up",
      });
      setIsLoading(false);
    }

    void loadDashboard();
    return () => {
      active = false;
    };
  }, [refreshVersion]);

  const userName = user?.full_name?.trim().split(/\s+/)[0] || user?.email?.split("@")[0] || "there";

  const tools = [
    {
      title: "Ask your workspace",
      description: "Chat across notes and document sources.",
      href: "/dashboard/chat",
      icon: Sparkles,
    },
    {
      title: "Explore connections",
      description: "Open the note and document relationship graph.",
      href: "/dashboard/knowledge-graph",
      icon: GitBranch,
    },
    {
      title: "Search everything",
      description: "Find matching notes, documents, and chats.",
      href: "/dashboard/search",
      icon: Search,
    },
    {
      title: "Workspace settings",
      description: "Choose appearance and your local AI model.",
      href: "/dashboard/settings",
      icon: Settings,
    },
  ];

  return (
    <div className="mx-auto max-w-[1400px] space-y-6">
      <OverviewHero
        userName={userName}
        noteCount={data.noteCount}
        documentCount={data.documentCount}
        chatCount={data.chatCount}
        aiReady={data.aiReady}
        isLoading={isLoading}
        onRefresh={() => setRefreshVersion((current) => current + 1)}
      />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(20rem,0.75fr)]">
        <div className="grid min-w-0 gap-5 lg:grid-cols-2">
          <RecentNotesPanel notes={data.notes} isLoading={isLoading} errorMessage={data.notesError} />
          <RecentDocumentsPanel documents={data.documents} isLoading={isLoading} errorMessage={data.documentsError} />
        </div>

        <RecentChatsPanel sessions={data.sessions} isLoading={isLoading} errorMessage={data.chatsError} />
      </div>

      <section className="border border-border bg-background">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-sm font-bold text-foreground">Workspace tools</h2>
        </div>
        <div className="grid sm:grid-cols-2 xl:grid-cols-4">
          {tools.map((tool) => {
            const Icon = tool.icon;
            return (
              <Link key={tool.title} href={tool.href} className="group flex min-h-24 items-start gap-3 border-b border-border p-4 hover:bg-muted sm:odd:border-r xl:border-b-0 xl:border-r xl:last:border-r-0">
                <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground group-hover:text-foreground" />
                <div>
                  <p className="text-sm font-medium text-foreground">{tool.title}</p>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">{tool.description}</p>
                </div>
              </Link>
            );
          })}
        </div>
      </section>
    </div>
  );
}
