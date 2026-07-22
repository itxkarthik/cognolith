import { apiConfig, tokenKeys } from "../../config/api";
import type { ChatMessageResponse } from "../../types";

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const prefix = `${encodeURIComponent(name)}=`;
  const value = document.cookie.split("; ").find((item) => item.startsWith(prefix));
  return value ? decodeURIComponent(value.slice(prefix.length)) : null;
}

export type ChatStreamEvent =
  | { type: "generation_started"; session_id: number; user_message: ChatMessageResponse; assistant_message: ChatMessageResponse }
  | { type: "retrieval_complete"; message_id: number; diagnostics: Record<string, unknown> | null }
  | { type: "token"; message_id: number; delta: string }
  | { type: "answer_reset"; message_id: number; reason: "grounding_repair" }
  | { type: "sources"; message_id: number; sources: ChatMessageResponse["sources"] }
  | { type: "completed"; message: ChatMessageResponse }
  | { type: "cancelled"; message: ChatMessageResponse }
  | { type: "error"; code: string; message: string; retryable: boolean; assistant_message_id: number };

export interface StreamOptions {
  signal?: AbortSignal;
  onEvent?: (event: ChatStreamEvent) => void;
  onError?: (error: Error) => void;
  onComplete?: () => void;
}

function parseFrame(frame: string): ChatStreamEvent | null {
  const lines = frame.replace(/\r\n/g, "\n").split("\n");
  let eventName = "message";
  const data: string[] = [];
  for (const line of lines) {
    if (!line || line.startsWith(":")) continue;
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (!data.length || eventName === "message") return null;
  const payload = JSON.parse(data.join("\n")) as Record<string, unknown>;
  return { type: eventName, ...payload } as ChatStreamEvent;
}

export async function parseSSEStream(response: Response, options: StreamOptions = {}): Promise<void> {
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${await response.text()}`);
  if (!response.body) throw new Error("Response body is empty");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      if (options.signal?.aborted) throw new DOMException("Stream aborted", "AbortError");
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      buffer = buffer.replace(/\r\n/g, "\n");
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const event = parseFrame(frame);
        if (event) options.onEvent?.(event);
      }
      if (done) break;
    }
    if (buffer.trim()) {
      const event = parseFrame(buffer);
      if (event) options.onEvent?.(event);
    }
    options.onComplete?.();
  } catch (value) {
    const error = value instanceof Error ? value : new Error(String(value));
    options.onError?.(error);
    throw error;
  } finally {
    reader.releaseLock();
  }
}

async function postStream(url: string, body: unknown, options: StreamOptions): Promise<void> {
  const csrf = readCookie(tokenKeys.csrf);
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (csrf) headers[apiConfig.csrfHeaderName] = csrf;
  const response = await fetch(url, {
    method: "POST",
    headers,
    credentials: "include",
    body: JSON.stringify(body),
    signal: options.signal,
  });
  await parseSSEStream(response, options);
}

export function streamChatMessage(sessionId: number, content: string, options: StreamOptions): Promise<void> {
  return postStream(`${apiConfig.streamBaseUrl}/chat/sessions/${sessionId}/messages/stream`, { content, role: "user" }, options);
}

export function retryChatMessage(sessionId: number, messageId: number, options: StreamOptions): Promise<void> {
  return postStream(`${apiConfig.streamBaseUrl}/chat/sessions/${sessionId}/messages/${messageId}/retry/stream`, {}, options);
}

export async function cancelStreamingMessage(sessionId: number, messageId: number): Promise<void> {
  const csrf = readCookie(tokenKeys.csrf);
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (csrf) headers[apiConfig.csrfHeaderName] = csrf;
  const response = await fetch(
    `${apiConfig.streamBaseUrl}/chat/sessions/${sessionId}/messages/${messageId}/cancel`,
    { method: "POST", headers, credentials: "include", body: "{}" }
  );
  if (!response.ok) throw new Error(`Cancellation failed with HTTP ${response.status}`);
}
