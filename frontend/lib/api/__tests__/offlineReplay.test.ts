import type { AxiosAdapter } from "axios";
import { afterEach, describe, expect, it } from "vitest";

import { apiClient, onOfflineReplay, processOfflineQueue, type OfflineReplayResult } from "../client";
import { requestQueue } from "@/lib/utils/requestQueue";

const OWNER = 7;
const originalAdapter = apiClient.defaults.adapter;

// Answers /users/me as `signedInId`; every other request gets `status` and `data`
function server(status: number, data: unknown = {}, signedInId = OWNER, sent: string[] = []): AxiosAdapter {
  return async (config) => {
    const isMe = config.url === "/users/me";
    if (!isMe) sent.push(`${config.method?.toUpperCase()} ${config.url}`);
    const code = isMe ? 200 : status;
    const response = { data: isMe ? { id: signedInId } : data, status: code, statusText: String(code), headers: {}, config };
    if (code >= 400) {
      throw Object.assign(new Error(`HTTP ${code}`), { isAxiosError: true, response, config });
    }
    return response;
  };
}

describe("replaying the offline queue", () => {
  afterEach(async () => {
    apiClient.defaults.adapter = originalAdapter;
    await requestQueue.clear();
  });

  it("reports a conflict instead of overwriting", async () => {
    requestQueue.add(OWNER, "PATCH", "/notes/1", { data: { content: "offline", expected_revision: 2 } });
    apiClient.defaults.adapter = server(409, { status: "error", error: "conflict", message: "changed" });
    const results: OfflineReplayResult[] = [];
    const stop = onOfflineReplay((_, result) => results.push(result));

    const outcome = await processOfflineQueue();
    stop();

    expect(outcome).toEqual({ succeeded: 0, failed: 0, conflicts: 1 });
    expect(results).toEqual([{ status: "conflict" }]);
    expect(requestQueue.isEmpty()).toBe(true);
  });

  it("hands the saved note to listeners", async () => {
    requestQueue.add(OWNER, "PATCH", "/notes/1", { data: { content: "offline", expected_revision: 2 } });
    apiClient.defaults.adapter = server(200, { id: 1, revision: 3 });
    const results: OfflineReplayResult[] = [];
    const stop = onOfflineReplay((_, result) => results.push(result));

    await processOfflineQueue();
    stop();

    expect(results).toEqual([{ status: "applied", data: { id: 1, revision: 3 } }]);
  });

  it("never sends another account's write", async () => {
    // Queued by account 7; another tab has since signed in as account 8
    requestQueue.add(OWNER, "POST", "/notes/", { data: { title: "private" } });
    const sent: string[] = [];
    apiClient.defaults.adapter = server(200, {}, 8, sent);

    const outcome = await processOfflineQueue();

    expect(sent).toEqual([]);
    expect(outcome).toEqual({ succeeded: 0, failed: 1, conflicts: 0 });
    expect(requestQueue.isEmpty()).toBe(true);
  });

  it("keeps the queue when it can't tell who is signed in", async () => {
    requestQueue.add(OWNER, "PATCH", "/notes/1", { data: { content: "offline" } });
    apiClient.defaults.adapter = async (config) => {
      throw Object.assign(new Error("Network Error"), { isAxiosError: true, config });
    };

    await processOfflineQueue();

    expect(requestQueue.size()).toBe(1);
  });
});
