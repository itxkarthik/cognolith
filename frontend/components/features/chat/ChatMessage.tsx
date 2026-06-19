"use client";

import { Bot, UserRound } from "lucide-react";

import type { ChatMessageResponse } from "@/types";

import { SourceReference } from "./SourceReference";

interface ChatMessageProps {
  message: ChatMessageResponse;
  isStreaming?: boolean;
}

export function ChatMessage({ message, isStreaming = false }: ChatMessageProps) {
  const isUser = message.role === "user";
  const timestamp = new Date(message.created_at).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[85%] border px-3 py-2 md:max-w-[78%] ${isUser ? "border-border bg-muted text-foreground" : "border-border bg-background text-foreground"}`}>
        <div className="mb-1.5 flex items-center justify-between gap-3 text-[10px] text-muted-foreground">
          <div className="flex items-center gap-1.5">
            {isUser ? <UserRound className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
            <span>{isUser ? "You" : "Assistant"}</span>
          </div>
          <span>{timestamp}</span>
        </div>

        <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">
          {message.content}
          {isStreaming ? <span className="ml-1 inline-block animate-pulse text-muted-foreground">|</span> : null}
        </p>

        {!isUser ? <SourceReference sources={message.sources} /> : null}
      </div>
    </div>
  );
}
