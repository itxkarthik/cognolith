interface QueuedRequest {
  id: string;
  method: string;
  url: string;
  config: Record<string, unknown>;
  timestamp: number;
}

export type { QueuedRequest };

class RequestQueue {
  private queue: Map<string, QueuedRequest> = new Map();
  private executing = false;

  add(method: string, url: string, config: Record<string, unknown>): string {
    const id = `${Date.now()}-${Math.random()}`;
    this.queue.set(id, { id, method, url, config, timestamp: Date.now() });
    return id;
  }

  remove(id: string): void {
    this.queue.delete(id);
  }

  getAll(): QueuedRequest[] {
    return Array.from(this.queue.values()).sort((a, b) => a.timestamp - b.timestamp);
  }

  isEmpty(): boolean {
    return this.queue.size === 0;
  }

  clear(): void {
    this.queue.clear();
  }

  size(): number {
    return this.queue.size;
  }

  async execute(onRequest: (req: QueuedRequest) => Promise<boolean>): Promise<void> {
    if (this.executing) return;
    this.executing = true;

    const requests = this.getAll();
    for (const req of requests) {
      try {
        const success = await onRequest(req);
        if (success) {
          this.remove(req.id);
        }
      } catch {
        break;
      }
    }

    this.executing = false;
  }
}

export const requestQueue = new RequestQueue();
