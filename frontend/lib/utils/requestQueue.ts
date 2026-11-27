/**
 * Writes made while offline, kept until the connection returns.
 *
 * The queue is persisted (IndexedDB in the browser) so a reload or closed tab does not
 * lose them. Repeated updates of one resource collapse into a single request, so a burst
 * of autosaves replays as one save; notes also carry `expected_revision`, so a replay
 * over newer changes is refused by the server instead of overwriting them.
 */

export interface QueuedRequest {
  id: string;
  method: string;
  url: string;
  data?: unknown;
  params?: unknown;
  timestamp: number;
}

export interface QueueStorage {
  load(): Promise<QueuedRequest[]>;
  put(request: QueuedRequest): Promise<void>;
  delete(id: string): Promise<void>;
  clear(): Promise<void>;
}

// "done": applied or permanently refused, drop it. "retry": keep it and stop, so later
// writes are not replayed ahead of it.
export type ReplayOutcome = "done" | "retry";

// Writes worth replaying later: editing notes, folders and tags. Others (sign-in, uploads,
// chat) fail at once rather than run unexpectedly minutes later.
const QUEUEABLE_URL = /^\/notes(\/|$)/;
const QUEUEABLE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export function isQueueable(method: string, url: string, data: unknown): boolean {
  return QUEUEABLE_METHODS.has(method.toUpperCase()) && QUEUEABLE_URL.test(url) && isSerializable(data);
}

function isSerializable(data: unknown): boolean {
  if (data === undefined || data === null) return true;
  if (typeof FormData !== "undefined" && data instanceof FormData) return false;
  if (typeof Blob !== "undefined" && data instanceof Blob) return false;
  if (data instanceof ArrayBuffer || ArrayBuffer.isView(data)) return false;
  if (typeof URLSearchParams !== "undefined" && data instanceof URLSearchParams) return false;
  try {
    JSON.stringify(data);
    return true;
  } catch {
    return false;
  }
}

function plainCopy<T>(value: T): T {
  return value === undefined ? value : (JSON.parse(JSON.stringify(value)) as T);
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export class RequestQueue {
  private queue = new Map<string, QueuedRequest>();
  private executing = false;
  private readonly loaded: Promise<void>;
  // Persistence runs in order, so a delete never lands before the put it follows
  private writes: Promise<void> = Promise.resolve();

  constructor(private readonly storage: QueueStorage) {
    this.loaded = storage
      .load()
      .then((stored) => {
        // Anything queued in this tab before loading finished takes precedence
        for (const request of stored) {
          if (!this.queue.has(request.id)) this.queue.set(request.id, request);
        }
      })
      .catch(() => undefined);
  }

  ready(): Promise<void> {
    return this.loaded;
  }

  /**
   * Queue a write. A PATCH to a resource that already has one queued is merged into it,
   * keeping its place in the order: the newer fields win.
   */
  add(method: string, url: string, config: { data?: unknown; params?: unknown } = {}): string {
    const upperMethod = method.toUpperCase();
    if (upperMethod === "PATCH") {
      const pending = this.getAll().find((request) => request.method === "PATCH" && request.url === url);
      if (pending) {
        const data =
          isPlainObject(pending.data) && isPlainObject(config.data)
            ? { ...pending.data, ...plainCopy(config.data) }
            : plainCopy(config.data);
        const merged: QueuedRequest = { ...pending, data, params: plainCopy(config.params) };
        this.queue.set(pending.id, merged);
        this.persist(() => this.storage.put(merged));
        return pending.id;
      }
    }
    const request: QueuedRequest = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      method: upperMethod,
      url,
      data: plainCopy(config.data),
      params: plainCopy(config.params),
      timestamp: Date.now(),
    };
    this.queue.set(request.id, request);
    this.persist(() => this.storage.put(request));
    return request.id;
  }

  remove(id: string): void {
    this.queue.delete(id);
    this.persist(() => this.storage.delete(id));
  }

  getAll(): QueuedRequest[] {
    return Array.from(this.queue.values()).sort((a, b) => a.timestamp - b.timestamp);
  }

  isEmpty(): boolean {
    return this.queue.size === 0;
  }

  size(): number {
    return this.queue.size;
  }

  async clear(): Promise<void> {
    this.queue.clear();
    this.persist(() => this.storage.clear());
    await this.writes;
  }

  /** Replay in order; stop at the first request that should be tried again later. */
  async execute(onRequest: (request: QueuedRequest) => Promise<ReplayOutcome>): Promise<void> {
    await this.loaded;
    if (this.executing) return;
    this.executing = true;
    try {
      for (const request of this.getAll()) {
        let outcome: ReplayOutcome;
        try {
          outcome = await onRequest(request);
        } catch {
          outcome = "retry";
        }
        if (outcome === "retry") break;
        // A newer edit merged in while this one was in flight was not sent: keep it
        if (this.queue.get(request.id) !== request) continue;
        this.remove(request.id);
      }
    } finally {
      this.executing = false;
    }
  }

  private persist(write: () => Promise<void>): void {
    this.writes = this.writes.then(write).catch(() => undefined);
  }
}

export function memoryStorage(): QueueStorage {
  const stored = new Map<string, QueuedRequest>();
  return {
    load: async () => Array.from(stored.values()),
    put: async (request) => void stored.set(request.id, request),
    delete: async (id) => void stored.delete(id),
    clear: async () => stored.clear(),
  };
}

const DB_NAME = "cognolith-offline";
const STORE_NAME = "requests";

export function indexedDbStorage(factory: IDBFactory): QueueStorage {
  let database: Promise<IDBDatabase> | null = null;
  const open = () => {
    database ??= new Promise((resolve, reject) => {
      const request = factory.open(DB_NAME, 1);
      request.onupgradeneeded = () => request.result.createObjectStore(STORE_NAME, { keyPath: "id" });
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    return database;
  };
  const run = async <T>(mode: IDBTransactionMode, operation: (store: IDBObjectStore) => IDBRequest<T>) => {
    const db = await open();
    return new Promise<T>((resolve, reject) => {
      const transaction = db.transaction(STORE_NAME, mode);
      const request = operation(transaction.objectStore(STORE_NAME));
      transaction.oncomplete = () => resolve(request.result);
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  };
  return {
    load: () => run("readonly", (store) => store.getAll() as IDBRequest<QueuedRequest[]>),
    put: async (request) => void (await run("readwrite", (store) => store.put(request))),
    delete: async (id) => void (await run("readwrite", (store) => store.delete(id))),
    clear: async () => void (await run("readwrite", (store) => store.clear())),
  };
}

// IndexedDB is missing during server rendering and may be blocked (some private modes);
// the queue then still works for the life of the tab.
export const requestQueue = new RequestQueue(
  typeof indexedDB === "undefined" ? memoryStorage() : indexedDbStorage(indexedDB),
);
