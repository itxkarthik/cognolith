"use client";

import { ArrowRight, Clock3, MessageSquarePlus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useChat } from "@/lib/hooks/useChat";

function formatDate(value: string): string {
  return new Date(value).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function ChatPage() {
  const router = useRouter();
  const { sessions, total, isLoading, isCreatingSession, error, fetchSessions, createSession } = useChat();

  useEffect(() => {
    void fetchSessions({ skip: 0, limit: 40 });
  }, [fetchSessions]);

  return (
    <div className="space-y-5">
      <section className="border border-border bg-background p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs text-muted-foreground">Conversations</p>
            <h1 className="mt-2 text-2xl font-bold text-foreground">Chat Sessions</h1>
            <p className="mt-1 text-sm text-muted-foreground">Manage your AI conversations and continue where you left off.</p>
            <p className="mt-2 text-xs text-muted-foreground">{total} {total === 1 ? "session" : "sessions"}</p>
          </div>

          <button
            type="button"
            onClick={() => {
              void createSession({ title: "New chat session" }).then((session) => {
                router.push(`/dashboard/chat/${session.id}`);
              });
            }}
            disabled={isCreatingSession}
            className="inline-flex items-center gap-2 rounded-sm border border-border bg-primary px-3 py-2 text-sm text-primary-foreground hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <MessageSquarePlus className="h-4 w-4" />
            New Session
          </button>
        </div>
      </section>

      {error ? <p className="rounded-sm border border-[#ff3b30] bg-[#ff3b30]/10 p-3 text-sm text-[#a50011]">{error}</p> : null}

      <section className="space-y-2">
        {isLoading ? (
          Array.from({ length: 8 }).map((_, index) => (
            <div key={index} className="h-20 animate-pulse border border-border bg-muted" />
          ))
        ) : sessions.length === 0 ? (
          <div className="border border-border bg-muted p-6 text-sm text-muted-foreground">
            No chat sessions yet. Create your first conversation to get started.
          </div>
        ) : (
          sessions.map((session) => {
            const lastMessage = session.messages[session.messages.length - 1];

            return (
              <Link key={session.id} href={`/dashboard/chat/${session.id}`} className="block border border-border bg-background p-4 hover:bg-muted">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="line-clamp-1 text-sm font-bold text-foreground">{session.title || `Session ${session.id}`}</h2>
                    <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{lastMessage?.content || "No messages yet"}</p>
                    <div className="mt-2 flex items-center gap-2 text-[11px] text-muted-foreground">
                      <Clock3 className="h-3.5 w-3.5" />
                      <span>{formatDate(session.last_message_at)}</span>
                    </div>
                  </div>

                  <ArrowRight className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
                </div>
              </Link>
            );
          })
        )}
      </section>
    </div>
  );
}
