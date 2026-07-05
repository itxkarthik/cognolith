import { describe, expect, it } from "vitest";

import {
  beginChatRequest,
  endChatRequest,
  isChatRequestPending,
  type PendingChatRequests,
} from "../chatRequestState";

describe("chat request state", () => {
  it("blocks a duplicate request for the same session", () => {
    const pending = beginChatRequest({}, 35);

    expect(isChatRequestPending(pending, 35)).toBe(true);
    expect(() => beginChatRequest(pending, 35)).toThrow("already being processed");
  });

  it("tracks different sessions independently", () => {
    const first = beginChatRequest({}, 35);
    const both = beginChatRequest(first, 36);

    expect(isChatRequestPending(both, 35)).toBe(true);
    expect(isChatRequestPending(both, 36)).toBe(true);
  });

  it("clears only the completed session request", () => {
    const pending: PendingChatRequests = { 35: true, 36: true };
    const remaining = endChatRequest(pending, 35);

    expect(isChatRequestPending(remaining, 35)).toBe(false);
    expect(isChatRequestPending(remaining, 36)).toBe(true);
  });
});
