import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ChatMessageResponse, ChatResponse, ChatSessionSummary } from "@/types";

vi.mock("@/lib/api/stream", () => ({
  streamChatMessage: vi.fn(),
  retryChatMessage: vi.fn(),
  cancelStreamingMessage: vi.fn(),
}));

const listChatSessions = vi.fn();
const getChatSessionById = vi.fn();
vi.mock("@/lib/api/chat", () => ({
  listChatSessions: (...args: unknown[]) => listChatSessions(...args),
  getChatSessionById: (...args: unknown[]) => getChatSessionById(...args),
  convertChatToNote: vi.fn(),
  createChatSession: vi.fn(),
}));

const { useChatStore, toSessionSummary } = await import("../chatStore");

const at = new Date(0).toISOString();

function message(id: number, role: "user" | "assistant", content: string): ChatMessageResponse {
  return { id, session_id: 7, role, content, created_at: at, updated_at: at };
}

const openSession: ChatResponse = {
  id: 7,
  user_id: 1,
  title: "Open chat",
  is_archived: false,
  is_pinned: false,
  last_message_at: at,
  created_at: at,
  updated_at: at,
  messages: [message(1, "user", "Hi"), message(2, "assistant", "Hello there")],
};

const listed: ChatSessionSummary = {
  ...toSessionSummary(openSession),
  title: "Renamed elsewhere",
};

describe("the chat session list", () => {
  beforeEach(() => {
    listChatSessions.mockReset();
    getChatSessionById.mockReset();
    useChatStore.setState({ sessions: [], total: 0, selectedSession: openSession, error: null });
  });

  it("keeps the open chat's messages when the list reloads", async () => {
    listChatSessions.mockResolvedValue({ data: [listed], count: 1, page_size: 30, has_more: false });

    await useChatStore.getState().fetchSessions();

    const state = useChatStore.getState();
    expect(state.sessions).toEqual([listed]);
    expect(state.selectedSession?.messages).toHaveLength(2);
  });

  it("lists a loaded session by its count and last non-empty message", async () => {
    getChatSessionById.mockResolvedValue({
      ...openSession,
      // A reply still streaming has no text yet
      messages: [...openSession.messages, message(3, "assistant", "")],
    });

    await useChatStore.getState().fetchSessionById(7);

    const [entry] = useChatStore.getState().sessions;
    expect(entry.message_count).toBe(3);
    expect(entry.last_message).toEqual({ role: "assistant", content: "Hello there" });
    expect("messages" in entry).toBe(false);
  });
});
