/**
 * Tests for the retry utility with exponential backoff
 */

import {
  retryWithExponentialBackoff,
  calculateDelay,
  isRetryableStatus,
  isRetryableError,
  DEFAULT_RETRY_CONFIG
} from "../retry";

describe("Retry Utility", () => {
  describe("calculateDelay", () => {
    it("should calculate exponential backoff correctly", () => {
      const config = {
        initialDelayMs: 100,
        backoffMultiplier: 2,
        jitterFactor: 0,
      };

      // First retry: 100ms
      const delay0 = calculateDelay(0, config);
      expect(delay0).toBe(100);

      // Second retry: 200ms
      const delay1 = calculateDelay(1, { ...config, jitterFactor: 0 });
      expect(delay1).toBe(200);

      // Third retry: 400ms
      const delay2 = calculateDelay(2, { ...config, jitterFactor: 0 });
      expect(delay2).toBe(400);
    });

    it("should respect maxDelayMs", () => {
      const config = {
        initialDelayMs: 100,
        maxDelayMs: 1000,
        backoffMultiplier: 2,
        jitterFactor: 0,
      };

      // Without max: 100 * 2^5 = 3200ms
      // With max: 1000ms
      const delay5 = calculateDelay(5, config);
      expect(delay5).toBeLessThanOrEqual(1000);
    });
  });

  describe("isRetryableStatus", () => {
    it("should return true for retryable status codes", () => {
      expect(isRetryableStatus(408)).toBe(true);
      expect(isRetryableStatus(429)).toBe(true);
      expect(isRetryableStatus(500)).toBe(true);
      expect(isRetryableStatus(502)).toBe(true);
      expect(isRetryableStatus(503)).toBe(true);
      expect(isRetryableStatus(504)).toBe(true);
    });

    it("should return false for non-retryable status codes", () => {
      expect(isRetryableStatus(401)).toBe(false);
      expect(isRetryableStatus(403)).toBe(false);
      expect(isRetryableStatus(404)).toBe(false);
      expect(isRetryableStatus(400)).toBe(false);
    });

    it("should return true for undefined (network error)", () => {
      expect(isRetryableStatus(undefined)).toBe(true);
    });
  });

  describe("isRetryableError", () => {
    it("should return true for network errors", () => {
      const error = new Error("Network error");
      expect(isRetryableError(error)).toBe(true);
    });

    it("should return false for CORS errors", () => {
      const error = new Error("CORS error");
      expect(isRetryableError(error)).toBe(false);
    });

    it("should check status code if response exists", () => {
      const retryableError = {
        response: { status: 500 },
      };
      expect(isRetryableError(retryableError)).toBe(true);

      const nonRetryableError = {
        response: { status: 404 },
      };
      expect(isRetryableError(nonRetryableError)).toBe(false);
    });
  });

  describe("retryWithExponentialBackoff", () => {
    it("should succeed on first attempt", async () => {
      const fn = jest.fn().mockResolvedValue("success");
      const result = await retryWithExponentialBackoff(fn);

      expect(result).toBe("success");
      expect(fn).toHaveBeenCalledTimes(1);
    });

    it("should retry and eventually succeed", async () => {
      let attempts = 0;
      const fn = jest.fn(async () => {
        attempts++;
        if (attempts < 3) {
          throw new Error("Temporary failure");
        }
        return "success";
      });

      const result = await retryWithExponentialBackoff(fn, {
        maxRetries: 5,
        initialDelayMs: 10,
        jitterFactor: 0,
      });

      expect(result).toBe("success");
      expect(fn).toHaveBeenCalledTimes(3);
    });

    it("should fail after max retries", async () => {
      const fn = jest.fn().mockRejectedValue(new Error("Persistent failure"));

      await expect(
        retryWithExponentialBackoff(fn, {
          maxRetries: 2,
          initialDelayMs: 10,
          jitterFactor: 0,
        })
      ).rejects.toThrow("Persistent failure");

      expect(fn).toHaveBeenCalledTimes(2);
    });
  });
});
