"use client";

import { ArrowRight, MessageSquareText } from "lucide-react";
import Link from "next/link";

import { extractPreview, formatDate } from "@/components/features/dashboard/utils";
import type { ChatResponse } from "@/types";

interface RecentChatsPanelProps {
  sessions: ChatResponse[];
  isLoading: boolean;
  errorMessage: string | null;
}

function latestMessage(session: ChatResponse): string {
  const message = session.messages[session.messages.length - 1];
  return message ? extractPreview(message.content, 110) : "No messages yet.";
}

export function RecentChatsPanel({ sessions, isLoading, errorMessage }: RecentChatsPanelProps) {
  return (
    <section className="border border-border bg-background">
      <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <MessageSquareText className="h-4 w-4 text-muted-foreground" />
          <h2 className="text-sm font-bold text-foreground">Recent conversations</h2>
        </div>
        <Link href="/dashboard/chat" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
          View all
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>

      {isLoading ? (
        <div className="space-y-3 p-4" aria-label="Loading recent conversations">
          {Array.from({ length: 3 }).map((_, index) => (
            <div key={index} className="space-y-2 border-b border-border pb-3 last:border-0 last:pb-0">
              <div className="h-3 w-1/2 animate-pulse bg-muted" />
              <div className="h-3 w-full animate-pulse bg-muted" />
            </div>
          ))}
        </div>
      ) : errorMessage ? (
        <p className="m-4 border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{errorMessage}</p>
      ) : sessions.length === 0 ? (
        <div className="p-6 text-center">
          <p className="text-sm font-medium text-foreground">No conversations yet</p>
          <p className="mt-1 text-xs text-muted-foreground">Ask a question across your notes and documents.</p>
          <Link href="/dashboard/chat" className="mt-4 inline-flex text-sm font-medium text-foreground underline underline-offset-4">
            Start chat
          </Link>
        </div>
      ) : (
        <div className="divide-y divide-border">
          {sessions.map((session) => (
            <Link key={session.id} href={`/dashboard/chat/${session.id}`} className="block px-4 py-3 hover:bg-muted">
              <div className="flex items-start justify-between gap-3">
                <p className="line-clamp-1 text-sm font-medium text-foreground">{session.title || "Untitled conversation"}</p>
                <span className="shrink-0 text-[11px] text-muted-foreground">{formatDate(session.last_message_at)}</span>
              </div>
              <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{latestMessage(session)}</p>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
