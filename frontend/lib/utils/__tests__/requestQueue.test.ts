import { describe, expect, it } from "vitest";

import {
  RequestQueue,
  isQueueable,
  memoryStorage,
  type QueuedRequest,
  type QueueStorage,
  type ReplayLocks,
} from "../requestQueue";

const OWNER = 7;

// One lock manager shared by "tabs" in a test, like navigator.locks across an origin
function sharedLocks(): ReplayLocks {
  let tail: Promise<unknown> = Promise.resolve();
  return {
    request<T>(_name: string, callback: () => Promise<T>): Promise<T> {
      const run = tail.then(callback);
      tail = run.catch(() => undefined);
      return run;
    },
  };
}

async function settled(queue: RequestQueue) {
  await queue.ready();
  // Let queued persistence writes run
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe("offline request queue", () => {
  it("replays in the order the writes were made", async () => {
    const queue = new RequestQueue(memoryStorage());
    queue.add(OWNER, "POST", "/notes/", { data: { title: "first" } });
    queue.add(OWNER, "DELETE", "/notes/3");
    const replayed: string[] = [];

    await queue.execute(async (request) => {
      replayed.push(`${request.method} ${request.url}`);
      return "done";
    });

    expect(replayed).toEqual(["POST /notes/", "DELETE /notes/3"]);
    expect(queue.isEmpty()).toBe(true);
  });

  it("collapses repeated saves of one note into the latest, in its original place", async () => {
    const queue = new RequestQueue(memoryStorage());
    queue.add(OWNER, "PATCH", "/notes/1", { data: { content: "a", is_pinned: true, expected_revision: 4 } });
    queue.add(OWNER, "POST", "/notes/", { data: { title: "other" } });
    queue.add(OWNER, "PATCH", "/notes/1", { data: { content: "abc", expected_revision: 4 } });

    const [first, second] = queue.getAll();

    expect(queue.size()).toBe(2);
    expect(first.url).toBe("/notes/1");
    expect(first.data).toEqual({ content: "abc", is_pinned: true, expected_revision: 4 });
    expect(second.url).toBe("/notes/");
  });

  it("keeps an edit merged into a save that was already being sent", async () => {
    const queue = new RequestQueue(memoryStorage());
    queue.add(OWNER, "PATCH", "/notes/1", { data: { content: "old" } });
    const sent: unknown[] = [];

    await queue.execute(async (request) => {
      sent.push(request.data);
      // Offline again while this save is in flight: the next autosave merges into it
      queue.add(OWNER, "PATCH", "/notes/1", { data: { content: "new" } });
      return "done";
    });

    expect(sent).toEqual([{ content: "old" }]);
    expect(queue.getAll().map((request) => request.data)).toEqual([{ content: "new" }]);
  });

  it("two tabs replaying at once send each write once", async () => {
    const storage = memoryStorage();
    const locks = sharedLocks();
    const firstTab = new RequestQueue(storage, locks);
    firstTab.add(OWNER, "POST", "/notes/", { data: { title: "offline" } });
    await settled(firstTab);
    // The second tab loads the same stored write
    const secondTab = new RequestQueue(storage, locks);
    await settled(secondTab);
    expect(secondTab.size()).toBe(1);
    const sent: string[] = [];
    const send = async (request: QueuedRequest) => {
      sent.push(request.id);
      return "done" as const;
    };

    await Promise.all([firstTab.execute(send), secondTab.execute(send)]);

    expect(sent).toHaveLength(1);
    expect(await storage.load()).toEqual([]);
  });

  it("does not replay what another tab cleared on logout", async () => {
    const storage = memoryStorage();
    const otherTab = new RequestQueue(storage);
    otherTab.add(OWNER, "POST", "/notes/", { data: { title: "private" } });
    await settled(otherTab);
    const loggingOut = new RequestQueue(storage);
    await settled(loggingOut);
    await loggingOut.clear();
    const sent: string[] = [];

    await otherTab.execute(async (request) => {
      sent.push(request.url);
      return "done";
    });

    expect(sent).toEqual([]);
  });

  it("does not merge saves made by different accounts", () => {
    const queue = new RequestQueue(memoryStorage());
    queue.add(OWNER, "PATCH", "/notes/1", { data: { content: "a" } });
    queue.add(8, "PATCH", "/notes/1", { data: { content: "b" } });

    expect(queue.getAll().map((request) => [request.ownerId, request.data])).toEqual([
      [OWNER, { content: "a" }],
      [8, { content: "b" }],
    ]);
  });

  it("stops at a write that must be retried and keeps everything after it", async () => {
    const queue = new RequestQueue(memoryStorage());
    queue.add(OWNER, "PATCH", "/notes/1", { data: { content: "a" } });
    queue.add(OWNER, "PATCH", "/notes/2", { data: { content: "b" } });
    const attempted: string[] = [];

    await queue.execute(async (request) => {
      attempted.push(request.url);
      return "retry";
    });

    expect(attempted).toEqual(["/notes/1"]);
    expect(queue.getAll().map((request) => request.url)).toEqual(["/notes/1", "/notes/2"]);
  });

  it("survives a reload through its storage", async () => {
    const storage = memoryStorage();
    const before = new RequestQueue(storage);
    before.add(OWNER, "PATCH", "/notes/1", { data: { content: "offline edit" } });
    await settled(before);

    const after = new RequestQueue(storage);
    await settled(after);

    expect(after.getAll().map((request) => request.data)).toEqual([{ content: "offline edit" }]);
  });

  it("clearing also empties the storage", async () => {
    const storage = memoryStorage();
    const queue = new RequestQueue(storage);
    queue.add(OWNER, "PATCH", "/notes/1", { data: {} });

    await queue.clear();

    expect(await storage.load()).toEqual([]);
  });

  it("keeps working when storage is unavailable", async () => {
    const failing: QueueStorage = {
      load: () => Promise.reject(new Error("blocked")),
      put: () => Promise.reject(new Error("blocked")),
      delete: () => Promise.reject(new Error("blocked")),
      clear: () => Promise.reject(new Error("blocked")),
    };
    const queue = new RequestQueue(failing);
    queue.add(OWNER, "PATCH", "/notes/1", { data: { content: "a" } });
    const replayed: QueuedRequest[] = [];

    await queue.execute(async (request) => {
      replayed.push(request);
      return "done";
    });

    expect(replayed).toHaveLength(1);
  });

  it("runs one replay at a time", async () => {
    const queue = new RequestQueue(memoryStorage());
    queue.add(OWNER, "POST", "/notes/", { data: {} });
    let calls = 0;
    const slow = async () => {
      calls++;
      await new Promise((resolve) => setTimeout(resolve, 20));
      return "done" as const;
    };

    await Promise.all([queue.execute(slow), queue.execute(slow)]);

    expect(calls).toBe(1);
  });

  it("only queues serializable note writes", () => {
    expect(isQueueable("PATCH", "/notes/1", { content: "x" })).toBe(true);
    expect(isQueueable("POST", "/notes/folders", { name: "x" })).toBe(true);
    expect(isQueueable("POST", "/documents/upload", new FormData())).toBe(false);
    expect(isQueueable("POST", "/notes/", new FormData())).toBe(false);
    expect(isQueueable("POST", "/login/access-token", {})).toBe(false);
    expect(isQueueable("POST", "/chat/sessions/1/messages", { content: "x" })).toBe(false);
  });
});
