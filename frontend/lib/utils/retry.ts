/**
 * Retry utility with exponential backoff and jitter
 * Used for handling transient network failures
 */

export interface RetryConfig {
  maxRetries: number;
  initialDelayMs: number;
  maxDelayMs: number;
  backoffMultiplier: number;
  jitterFactor: number; // 0-1, adds randomness to prevent thundering herd
}

export const DEFAULT_RETRY_CONFIG: RetryConfig = {
  maxRetries: 3,
  initialDelayMs: 100,
  maxDelayMs: 10000,
  backoffMultiplier: 2,
  jitterFactor: 0.1,
};

/**
 * Calculate delay with exponential backoff and jitter
 */
export function calculateDelay(
  attempt: number,
  config: Partial<RetryConfig> = {}
): number {
  const finalConfig = { ...DEFAULT_RETRY_CONFIG, ...config };

  // Exponential backoff: delay = initialDelay * (backoffMultiplier ^ attempt)
  const exponentialDelay = Math.min(
    finalConfig.initialDelayMs * Math.pow(finalConfig.backoffMultiplier, attempt),
    finalConfig.maxDelayMs
  );

  // Add jitter: randomness between 0 and (exponentialDelay * jitterFactor)
  const jitter = Math.random() * exponentialDelay * finalConfig.jitterFactor;

  return exponentialDelay + jitter;
}

/**
 * Retry function with exponential backoff
 * Retries on transient failures (network errors, 5xx, timeouts)
 */
export async function retryWithExponentialBackoff<T>(
  fn: () => Promise<T>,
  config: Partial<RetryConfig> = {}
): Promise<T> {
  const finalConfig = { ...DEFAULT_RETRY_CONFIG, ...config };
  let lastError: Error | undefined;

  for (let attempt = 0; attempt < finalConfig.maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));

      // Don't retry on last attempt
      if (attempt === finalConfig.maxRetries - 1) {
        throw lastError;
      }

      // Calculate delay and wait
      const delayMs = calculateDelay(attempt, finalConfig);

      console.debug(
        `[Retry] Attempt ${attempt + 1}/${finalConfig.maxRetries} failed, ` +
        `retrying in ${delayMs.toFixed(0)}ms. Error: ${lastError.message}`
      );

      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }

  // This should never happen, but just in case
  throw lastError || new Error("Max retries exceeded");
}

/**
 * Check if an HTTP status code is retryable
 */
export function isRetryableStatus(status?: number): boolean {
  if (!status) return true; // Network error, retry

  // Retryable status codes:
  // 408: Request Timeout
  // 429: Too Many Requests (Rate Limit)
  // 500: Internal Server Error
  // 502: Bad Gateway
  // 503: Service Unavailable
  // 504: Gateway Timeout
  const retryableStatuses = [408, 429, 500, 502, 503, 504];

  return retryableStatuses.includes(status);
}

/**
 * Check if an axios error is retryable
 */
interface RetryableErrorLike {
  response?: { status?: number };
  message?: string;
}

export function isRetryableError(error: unknown, method?: string): boolean {
  const normalizedMethod = method?.toUpperCase();
  if (normalizedMethod && ["POST", "PATCH"].includes(normalizedMethod)) {
    return false;
  }

  const candidate = error as RetryableErrorLike;

  // No response = network error
  if (!candidate.response) {
    // Don't retry CORS errors
    if (candidate.message?.includes("CORS")) {
      return false;
    }
    return true;
  }

  // Check status code
  return isRetryableStatus(candidate.response.status);
}
