import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ChatStreamEvent, StreamOptions } from "@/lib/api/stream";

const notStarted: ChatStreamEvent = {
  type: "error",
  code: "GENERATION_NOT_STARTED",
  message: "A reply is already being generated.",
  retryable: false,
  assistant_message_id: null,
};

const replay = async (_sessionId: number, _arg: unknown, options: StreamOptions) => {
  options.onEvent?.(notStarted);
};

vi.mock("@/lib/api/stream", () => ({
  streamChatMessage: vi.fn(replay),
  retryChatMessage: vi.fn(replay),
  cancelStreamingMessage: vi.fn(),
}));

const getChatSessionById = vi.fn();
vi.mock("@/lib/api/chat", () => ({
  getChatSessionById: (...args: unknown[]) => getChatSessionById(...args),
  convertChatToNote: vi.fn(),
  createChatSession: vi.fn(),
  listChatSessions: vi.fn(),
}));

const { useChatStore } = await import("../chatStore");

describe("a reply that never started", () => {
  beforeEach(() => {
    getChatSessionById.mockReset();
    useChatStore.setState({
      selectedSession: {
        id: 7,
        title: "Chat",
        messages: [],
        last_message_at: new Date(0).toISOString(),
      } as never,
      pendingMessageRequests: {},
      error: null,
    });
  });

  it("rejects the send instead of returning an older reply", async () => {
    await expect(useChatStore.getState().sendMessage(7, "Hello")).rejects.toThrow(
      "already being generated",
    );

    expect(getChatSessionById).not.toHaveBeenCalled();
    expect(useChatStore.getState().selectedSession?.messages).toEqual([]);
  });

  it("rejects the retry with the server's reason", async () => {
    await expect(useChatStore.getState().retryMessage(7, 3)).rejects.toThrow(
      "already being generated",
    );
  });
});
