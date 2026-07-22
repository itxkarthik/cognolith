"use client";

import { Bot, RefreshCw, UserRound } from "lucide-react";

import type { ChatMessageResponse } from "@/types";

import { SourceReference } from "./SourceReference";
import { RetrievalDiagnostics } from "./RetrievalDiagnostics";

interface ChatMessageProps {
  message: ChatMessageResponse;
  isStreaming?: boolean;
  onRetry?: (messageId: number) => Promise<void>;
}

export function ChatMessage({ message, isStreaming = false, onRetry }: ChatMessageProps) {
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
        {!isUser && message.generation_metadata?.repairing && isStreaming ? <p className="mt-2 text-xs text-muted-foreground">Improving grounding...</p> : null}
        {!isUser && (message.generation_status === "cancelled" || message.generation_status === "failed") ? (
          <div className="mt-2 flex items-center gap-2 border-t border-border pt-2 text-xs text-muted-foreground">
            <span>{message.generation_status === "cancelled" ? "Stopped" : "Response failed"}</span>
            {onRetry ? <button type="button" onClick={() => void onRetry(message.id)} className="inline-flex items-center gap-1 text-foreground hover:underline"><RefreshCw className="h-3 w-3" /> Retry</button> : null}
          </div>
        ) : null}
        {!isUser ? <RetrievalDiagnostics metadata={message.generation_metadata} /> : null}
      </div>
    </div>
  );
}
