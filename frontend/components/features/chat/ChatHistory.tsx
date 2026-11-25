"use client";

import { useEffect, useMemo, useRef } from "react";

import { orderChatThread } from "@/lib/chatThread";
import type { ChatMessageResponse } from "@/types";

import { ChatMessage } from "./ChatMessage";

interface ChatHistoryProps {
  messages: ChatMessageResponse[];
  isLoading?: boolean;
  streamingMessageId?: number | null;
  onRetry?: (messageId: number) => Promise<void>;
}

export function ChatHistory({ messages, isLoading = false, streamingMessageId = null, onRetry }: ChatHistoryProps) {
  const bottomAnchorRef = useRef<HTMLDivElement | null>(null);
  const threadRef = useRef<HTMLDivElement | null>(null);
  // Retried replies sit next to their question, not at the end
  const orderedMessages = useMemo(() => orderChatThread(messages), [messages]);

  useEffect(() => {
    const last = orderedMessages[orderedMessages.length - 1];
    if (streamingMessageId !== null && last?.id !== streamingMessageId) {
      // A retry of an earlier reply streams mid-thread; follow it there
      threadRef.current
        ?.querySelector(`[data-message-id="${streamingMessageId}"]`)
        ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      return;
    }
    bottomAnchorRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [orderedMessages, streamingMessageId]);

  if (isLoading && messages.length === 0) {
    return (
      <section className="h-[56vh] space-y-2 overflow-y-auto border border-border bg-background p-3">
        {Array.from({ length: 6 }).map((_, index) => (
          <div key={index} className="h-16 animate-pulse border border-border bg-muted" />
        ))}
      </section>
    );
  }

  return (
    <section className="h-[56vh] overflow-y-auto border border-border bg-background p-3">
      {messages.length === 0 ? (
        <div className="flex h-full items-center justify-center border border-dashed border-border bg-muted p-5 text-sm text-muted-foreground">
          Ask naturally. Workspace questions use your notes and documents when relevant.
        </div>
      ) : (
        <div ref={threadRef} className="space-y-3">
          {orderedMessages.map((message) => (
            <div key={message.id} data-message-id={message.id}>
              <ChatMessage message={message} isStreaming={streamingMessageId === message.id} onRetry={onRetry} />
            </div>
          ))}
          <div ref={bottomAnchorRef} />
        </div>
      )}
    </section>
  );
}
