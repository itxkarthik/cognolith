"use client";

import { ArrowUp, Square } from "lucide-react";
import { useRef, useState } from "react";

interface ChatInputProps {
  onSend: (content: string) => Promise<void>;
  disabled?: boolean;
  isGenerating?: boolean;
  onCancel?: () => Promise<void>;
}

export function ChatInput({ onSend, disabled = false, isGenerating = false, onCancel }: ChatInputProps) {
  const [content, setContent] = useState("");
  const isSubmittingRef = useRef(false);

  const handleSubmit = async () => {
    const trimmed = content.trim();
    if (!trimmed || disabled || isSubmittingRef.current) return;

    isSubmittingRef.current = true;
    try {
      await onSend(trimmed);
      setContent("");
    } catch {
      // The page displays the request error. Keep the draft available for retry.
    } finally {
      isSubmittingRef.current = false;
    }
  };

  return (
    <section className="border border-border bg-background p-3">
      <div className="flex items-end gap-2">
        <textarea
          value={content}
          onChange={(event) => setContent(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void handleSubmit();
            }
          }}
          rows={3}
          disabled={disabled}
          placeholder="Ask about your workspace or anything else..."
          className="w-full resize-none rounded-sm border border-border bg-muted px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-ring focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
        />

        <button
          type="button"
          onClick={() => { void (isGenerating ? onCancel?.() : handleSubmit()); }}
          disabled={isGenerating ? !onCancel : disabled || !content.trim()}
          className={`inline-flex h-10 w-10 items-center justify-center rounded-sm border text-primary-foreground disabled:cursor-not-allowed disabled:opacity-50 ${isGenerating ? "border-destructive bg-destructive hover:bg-destructive/90" : "border-border bg-primary hover:bg-primary/90"}`}
          aria-label={isGenerating ? "Stop response" : "Send message"}
        >
          {isGenerating ? <Square className="h-3.5 w-3.5 fill-current" /> : <ArrowUp className="h-4 w-4" />}
        </button>
      </div>
    </section>
  );
}
