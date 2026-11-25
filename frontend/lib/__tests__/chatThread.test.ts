import { describe, expect, it } from "vitest";

import type { ChatMessageResponse } from "@/types";

import { orderChatThread } from "../chatThread";

function message(
  id: number,
  role: "user" | "assistant",
  metadata: Record<string, unknown> | null = null
): ChatMessageResponse {
  return {
    id,
    session_id: 1,
    role,
    content: `message ${id}`,
    created_at: `2026-10-24T10:00:${String(id).padStart(2, "0")}Z`,
    updated_at: `2026-10-24T10:00:${String(id).padStart(2, "0")}Z`,
    generation_metadata: metadata,
  };
}

const ids = (messages: ChatMessageResponse[]) => messages.map((item) => item.id);

describe("orderChatThread", () => {
  it("keeps a normal conversation in chronological order", () => {
    const thread = [
      message(1, "user"),
      message(2, "assistant", { reply_to_message_id: 1 }),
      message(3, "user"),
      message(4, "assistant", { reply_to_message_id: 3 }),
    ];

    expect(ids(orderChatThread(thread))).toEqual([1, 2, 3, 4]);
  });

  it("places a retry of an earlier reply next to its question", () => {
    const thread = [
      message(1, "user"),
      message(2, "assistant", { reply_to_message_id: 1 }),
      message(3, "user"),
      message(4, "assistant", { reply_to_message_id: 3 }),
      message(5, "assistant", { retry_of: 2, reply_to_message_id: 1 }),
    ];

    expect(ids(orderChatThread(thread))).toEqual([1, 2, 5, 3, 4]);
  });

  it("follows the retry chain for replies saved before reply_to existed", () => {
    const thread = [
      message(1, "user"),
      message(2, "assistant"),
      message(3, "user"),
      message(4, "assistant"),
      message(5, "assistant", { retry_of: 2 }),
      message(6, "assistant", { retry_of: 5 }),
    ];

    expect(ids(orderChatThread(thread))).toEqual([1, 2, 5, 6, 3, 4]);
  });

  it("leaves replies in place when their question is not loaded", () => {
    const thread = [
      message(3, "user"),
      message(4, "assistant", { reply_to_message_id: 1 }),
    ];

    expect(ids(orderChatThread(thread))).toEqual([3, 4]);
  });

  it("does not drop messages when metadata forms a cycle", () => {
    const thread = [
      message(1, "user"),
      message(2, "assistant", { retry_of: 3 }),
      message(3, "assistant", { retry_of: 2 }),
    ];

    expect(ids(orderChatThread(thread)).sort()).toEqual([1, 2, 3]);
  });
});
