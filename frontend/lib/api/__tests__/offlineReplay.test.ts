import type { AxiosAdapter } from "axios";
import { afterEach, describe, expect, it } from "vitest";

import { apiClient, onOfflineReplay, processOfflineQueue, type OfflineReplayResult } from "../client";
import { requestQueue } from "@/lib/utils/requestQueue";

const originalAdapter = apiClient.defaults.adapter;

function respondWith(status: number, data: unknown = {}): AxiosAdapter {
  return async (config) => {
    const response = { data, status, statusText: String(status), headers: {}, config };
    if (status >= 400) {
      throw Object.assign(new Error(`HTTP ${status}`), { isAxiosError: true, response, config });
    }
    return response;
  };
}

describe("replaying the offline queue", () => {
  afterEach(async () => {
    apiClient.defaults.adapter = originalAdapter;
    await requestQueue.clear();
  });

  it("reports a conflict instead of overwriting, and drops the write", async () => {
    requestQueue.add("PATCH", "/notes/1", { data: { content: "offline", expected_revision: 2 } });
    apiClient.defaults.adapter = respondWith(409, { status: "error", error: "conflict", message: "changed" });
    const results: OfflineReplayResult[] = [];
    const stop = onOfflineReplay((_, result) => results.push(result));

    const outcome = await processOfflineQueue();
    stop();

    expect(outcome).toEqual({ succeeded: 0, failed: 0, conflicts: 1 });
    expect(results).toEqual([{ status: "conflict" }]);
    expect(requestQueue.isEmpty()).toBe(true);
  });

  it("hands the saved note to listeners", async () => {
    requestQueue.add("PATCH", "/notes/1", { data: { content: "offline", expected_revision: 2 } });
    apiClient.defaults.adapter = respondWith(200, { id: 1, revision: 3 });
    const results: OfflineReplayResult[] = [];
    const stop = onOfflineReplay((_, result) => results.push(result));

    await processOfflineQueue();
    stop();

    expect(results).toEqual([{ status: "applied", data: { id: 1, revision: 3 } }]);
  });
});
