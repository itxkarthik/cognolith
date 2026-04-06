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
  const {
    sessions,
    total,
    isLoading,
    isCreatingSession,
    error,
    fetchSessions,
    createSession,
  } = useChat();

  useEffect(() => {
    void fetchSessions({ skip: 0, limit: 40 });
  }, [fetchSessions]);

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-zinc-800 bg-[#0f1930]/80 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.22em] text-zinc-500">Conversations</p>
            <h1 className="mt-2 text-2xl font-semibold text-[#dee5ff]">Chat Sessions</h1>
            <p className="mt-1 text-sm text-zinc-400">
              Manage your AI conversations and continue where you left off.
            </p>
            <p className="mt-2 text-xs uppercase tracking-[0.14em] text-zinc-500">
              {total} {total === 1 ? "session" : "sessions"}
            </p>
          </div>

          <button
            type="button"
            onClick={() => {
              void createSession({ title: "New chat session" }).then((session) => {
                router.push(`/dashboard/chat/${session.id}`);
              });
            }}
            disabled={isCreatingSession}
            className="inline-flex items-center gap-2 rounded-lg border border-[#4f5a8f] bg-[#18233f] px-3 py-2 text-sm text-[#dbe3ff] transition hover:border-[#94aaff]/45 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <MessageSquarePlus className="h-4 w-4" />
            New Session
          </button>
        </div>
      </section>

      {error ? (
        <p className="rounded-lg border border-rose-900/50 bg-rose-950/30 p-3 text-sm text-rose-200">
          {error}
        </p>
      ) : null}

      <section className="space-y-2">
        {isLoading ? (
          Array.from({ length: 8 }).map((_, index) => (
            <div
              key={index}
              className="h-20 animate-pulse rounded-xl border border-zinc-800 bg-[#0f1930]/80"
            />
          ))
        ) : sessions.length === 0 ? (
          <div className="rounded-xl border border-zinc-800 bg-[#0f1930]/80 p-6 text-sm text-zinc-400">
            No chat sessions yet. Create your first conversation to get started.
          </div>
        ) : (
          sessions.map((session) => {
            const lastMessage = session.messages[session.messages.length - 1];

            return (
              <Link
                key={session.id}
                href={`/dashboard/chat/${session.id}`}
                className="block rounded-xl border border-zinc-800 bg-[#0f1930]/80 p-4 transition hover:border-zinc-600"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="line-clamp-1 text-sm font-semibold text-zinc-100">
                      {session.title || `Session ${session.id}`}
                    </h2>
                    <p className="mt-1 line-clamp-2 text-xs text-zinc-400">
                      {lastMessage?.content || "No messages yet"}
                    </p>
                    <div className="mt-2 flex items-center gap-2 text-[11px] uppercase tracking-[0.1em] text-zinc-500">
                      <Clock3 className="h-3.5 w-3.5" />
                      <span>{formatDate(session.last_message_at)}</span>
                    </div>
                  </div>

                  <ArrowRight className="h-4 w-4 flex-shrink-0 text-zinc-500" />
                </div>
              </Link>
            );
          })
        )}
      </section>
    </div>
  );
}