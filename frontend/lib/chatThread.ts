import type { ChatMessageResponse } from "@/types";

function metadataId(message: ChatMessageResponse, key: string): number | null {
  const value = message.generation_metadata?.[key];
  return typeof value === "number" ? value : null;
}

/**
 * Display order for a chat thread: every assistant reply directly follows the
 * question it answers, so a retry of an earlier reply appears next to that
 * question instead of at the end. Replies to the same question stay chronological.
 *
 * Replies record `reply_to_message_id`; older retries only have `retry_of`, so
 * they are placed after the reply they retried.
 */
export function orderChatThread(messages: ChatMessageResponse[]): ChatMessageResponse[] {
  const byId = new Map(messages.map((message) => [message.id, message]));
  const children = new Map<number, ChatMessageResponse[]>();
  const roots: ChatMessageResponse[] = [];

  for (const message of messages) {
    const anchor = message.role === "assistant" ? anchorOf(message, byId) : null;
    if (anchor === null) {
      roots.push(message);
      continue;
    }
    const siblings = children.get(anchor) ?? [];
    siblings.push(message);
    children.set(anchor, siblings);
  }

  const ordered: ChatMessageResponse[] = [];
  const placed = new Set<number>();
  const place = (message: ChatMessageResponse) => {
    if (placed.has(message.id)) return;
    placed.add(message.id);
    ordered.push(message);
    for (const child of children.get(message.id) ?? []) place(child);
  };
  roots.forEach(place);
  // Anything left (an anchor cycle in bad data) keeps its chronological place at the end
  messages.forEach(place);
  return ordered;
}

function anchorOf(
  message: ChatMessageResponse,
  byId: Map<number, ChatMessageResponse>
): number | null {
  const replyTo = metadataId(message, "reply_to_message_id");
  if (replyTo !== null && replyTo !== message.id && byId.has(replyTo)) return replyTo;

  const retryOf = metadataId(message, "retry_of");
  if (retryOf !== null && retryOf !== message.id && byId.has(retryOf)) return retryOf;

  return null;
}
