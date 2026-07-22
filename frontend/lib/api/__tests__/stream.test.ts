import { describe, expect, it, vi } from "vitest";

import { parseSSEStream } from "../stream";

function streamedResponse(parts: string[]): Response {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        for (const part of parts) controller.enqueue(encoder.encode(part));
        controller.close();
      },
    }),
    { status: 200, headers: { "Content-Type": "text/event-stream" } }
  );
}

describe("parseSSEStream", () => {
  it("parses named JSON events split across network chunks", async () => {
    const onEvent = vi.fn();
    const response = streamedResponse([
      'event: token\ndata: {"message_id":2,"del',
      'ta":"hello"}\n\nevent: completed\ndata: {"message":{"id":2}}\n\n',
    ]);

    await parseSSEStream(response, { onEvent });

    expect(onEvent).toHaveBeenNthCalledWith(1, {
      type: "token",
      message_id: 2,
      delta: "hello",
    });
    expect(onEvent).toHaveBeenNthCalledWith(2, {
      type: "completed",
      message: { id: 2 },
    });
  });

  it("ignores heartbeat comments and accepts CRLF framing", async () => {
    const onEvent = vi.fn();
    const response = streamedResponse([
      ': connected\r\n\r\nevent: answer_reset\r\ndata: {"message_id":2,"reason":"grounding_repair"}\r\n\r\n',
    ]);

    await parseSSEStream(response, { onEvent });

    expect(onEvent).toHaveBeenCalledOnce();
    expect(onEvent.mock.calls[0][0].type).toBe("answer_reset");
  });
});
