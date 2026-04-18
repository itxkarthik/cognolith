import { describe, it, expect, beforeEach, vi } from 'vitest';
import { requestQueue } from '@/lib/utils/requestQueue';

describe('Offline Detection & Request Queueing', () => {
  beforeEach(() => {
    requestQueue.clear();
  });

  it('should queue a request when adding', () => {
    requestQueue.add('POST', '/api/notes', { data: { title: 'Test' } });
    expect(requestQueue.size()).toBe(1);
  });

  it('should return all queued requests in order', () => {
    requestQueue.add('POST', '/api/notes', { data: { title: 'Note 1' } });
    requestQueue.add('POST', '/api/notes', { data: { title: 'Note 2' } });

    const all = requestQueue.getAll();
    expect(all.length).toBe(2);
    expect(all[0].timestamp <= all[1].timestamp).toBe(true);
  });

  it('should remove a request from queue', () => {
    const id = requestQueue.add('POST', '/api/notes', { data: { title: 'Test' } });
    requestQueue.remove(id);
    expect(requestQueue.isEmpty()).toBe(true);
  });

  it('should return true when queue is empty', () => {
    expect(requestQueue.isEmpty()).toBe(true);
    requestQueue.add('POST', '/api/notes', { data: {} });
    expect(requestQueue.isEmpty()).toBe(false);
  });

  it('should clear all requests', () => {
    requestQueue.add('POST', '/api/notes', { data: {} });
    requestQueue.add('PUT', '/api/documents/1', { data: {} });
    requestQueue.clear();
    expect(requestQueue.size()).toBe(0);
  });

  it('should execute queued requests in order', async () => {
    const executed: string[] = [];

    requestQueue.add('POST', '/api/notes', { data: { id: 1 } });
    requestQueue.add('POST', '/api/notes', { data: { id: 2 } });

    await requestQueue.execute(async (req) => {
      executed.push(req.config.data.id);
      return true;
    });

    expect(executed).toEqual([1, 2]);
    expect(requestQueue.isEmpty()).toBe(true);
  });

  it('should prevent concurrent execution', async () => {
    const callCount = { value: 0 };

    requestQueue.add('POST', '/api/notes', { data: {} });

    const promise1 = requestQueue.execute(async () => {
      callCount.value++;
      await new Promise(resolve => setTimeout(resolve, 100));
      return true;
    });

    const promise2 = requestQueue.execute(async () => {
      callCount.value++;
      return true;
    });

    await Promise.all([promise1, promise2]);
    expect(callCount.value).toBe(1);
  });
});
