export type PendingChatRequests = Record<number, true>;

export function isChatRequestPending(
  pending: PendingChatRequests,
  sessionId: number
): boolean {
  return pending[sessionId] === true;
}

export function beginChatRequest(
  pending: PendingChatRequests,
  sessionId: number
): PendingChatRequests {
  if (isChatRequestPending(pending, sessionId)) {
    throw new Error("A message is already being processed for this session.");
  }

  return { ...pending, [sessionId]: true };
}

export function endChatRequest(
  pending: PendingChatRequests,
  sessionId: number
): PendingChatRequests {
  const next = { ...pending };
  delete next[sessionId];
  return next;
}
