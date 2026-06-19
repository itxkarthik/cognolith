"use client";

import { useEffect, useRef } from "react";

import type { ChatMessageResponse } from "@/types";

import { ChatMessage } from "./ChatMessage";

interface ChatHistoryProps {
  messages: ChatMessageResponse[];
  isLoading?: boolean;
  streamingMessageId?: number | null;
}

export function ChatHistory({ messages, isLoading = false, streamingMessageId = null }: ChatHistoryProps) {
  const bottomAnchorRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomAnchorRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, streamingMessageId]);

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
          Start with a question. Answers will include source references from your library.
        </div>
      ) : (
        <div className="space-y-3">
          {messages.map((message) => (
            <ChatMessage key={message.id} message={message} isStreaming={streamingMessageId === message.id} />
          ))}
          <div ref={bottomAnchorRef} />
        </div>
      )}
    </section>
  );
}
