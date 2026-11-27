import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";

import { apiConfig, tokenKeys, getTimeoutForEndpoint } from "@/config/api";
import { useAuthStore } from "@/store/authStore";
import { isRetryableError, retryWithExponentialBackoff, DEFAULT_RETRY_CONFIG } from "@/lib/utils/retry";
import { isQueueable, requestQueue, type QueuedRequest } from "@/lib/utils/requestQueue";
import type { ApiError } from "@/types";

type RequestWithRetry = InternalAxiosRequestConfig & {
	_retry?: boolean;
};

export class APIRequestError extends Error {
	statusCode?: number;
	errorCode?: string;
	requestId?: string;
	details?: ApiError["details"];

	constructor(
		message: string,
		options?: {
			statusCode?: number;
			errorCode?: string;
			requestId?: string;
			details?: ApiError["details"];
		}
	) {
		super(message);
		this.name = "APIRequestError";
		this.statusCode = options?.statusCode;
		this.errorCode = options?.errorCode;
		this.requestId = options?.requestId;
		this.details = options?.details;
	}
}

function normalizeErrorMessage(data: ApiError | undefined, fallback: string): string {
	if (!data) {
		return fallback;
	}

	if (typeof data.message === "string" && data.message.trim()) {
		return data.message;
	}

	if (typeof data.detail === "string" && data.detail.trim()) {
		return data.detail;
	}

	if (Array.isArray(data.details) && data.details.length > 0) {
		return data.details.map((item) => item.message).join("; ");
	}

	if (Array.isArray(data.detail)) {
		const extracted = data.detail
			.map((item) => {
				if (typeof item === "string") {
					return item;
				}
				if (item && typeof item === "object" && "msg" in item) {
					return String((item as { msg: unknown }).msg);
				}
				return null;
			})
			.filter((item): item is string => Boolean(item));
		if (extracted.length > 0) {
			return extracted.join("; ");
		}
	}

	if (data.detail && typeof data.detail === "object") {
		try {
			return JSON.stringify(data.detail);
		} catch {
			return fallback;
		}
	}

	return fallback;
}

export function readCookie(name: string): string | null {
	if (typeof document === "undefined") {
		return null;
	}

	const cookie = document.cookie
		.split("; ")
		.find((row) => row.startsWith(`${name}=`));

	if (!cookie) {
		return null;
	}

	return decodeURIComponent(cookie.substring(name.length + 1));
}

export const apiClient = axios.create({
	baseURL: apiConfig.baseUrl,
	timeout: apiConfig.timeoutMs,
	withCredentials: true,
	headers: {
		"Content-Type": "application/json",
	},
});

const refreshClient = axios.create({
	baseURL: apiConfig.baseUrl,
	timeout: apiConfig.timeoutMs,
	withCredentials: true,
	headers: {
		"Content-Type": "application/json",
	},
});

declare module "axios" {
	interface AxiosRequestConfig {
		// Set on queue replays, which must not be queued again
		offlineReplay?: boolean;
	}
}

apiClient.interceptors.request.use((config) => {
	const isOnline = typeof navigator === "undefined" || navigator.onLine;
	const method = (config.method ?? "get").toUpperCase();

	if (!isOnline && !config.offlineReplay && method !== "GET" && method !== "HEAD" && method !== "OPTIONS") {
		const url = config.url || "";
		if (!isQueueable(method, url, config.data)) {
			return Promise.reject(
				new APIRequestError("You are offline. Try again once the connection is back.", {
					statusCode: 0,
					errorCode: "OFFLINE",
				})
			);
		}
		requestQueue.add(method, url, { data: config.data, params: config.params });
		return Promise.reject(
			new APIRequestError("Saved offline; it will sync when the connection is back.", {
				statusCode: 0,
				errorCode: "OFFLINE_QUEUED",
			})
		);
	}

	// Apply endpoint-specific timeout based on method and URL
	if (config.url && config.method) {
		const timeout = getTimeoutForEndpoint(config.method, config.url);
		config.timeout = timeout;
	}

	// Preserve trailing slashes for endpoints that need them
	if (config.url) {
		// For documents endpoints that match /documents or /documents/upload etc
		if (config.url.match(/^\/documents([/?]|$)/) && !config.url.endsWith("/") && config.url !== "/documents/upload") {
			// Add trailing slash if not present and it's a GET request with params
			if (config.method?.toLowerCase() === "get" && config.params && Object.keys(config.params).length > 0) {
				config.url = config.url + "/";
			}
		}
	}

	// Let browser set multipart boundaries automatically.
	if (typeof FormData !== "undefined" && config.data instanceof FormData) {
		config.headers = config.headers ?? {};
		delete config.headers["Content-Type"];
	}

	if (method === "GET" || method === "HEAD" || method === "OPTIONS") {
		return config;
	}

	const csrfToken = readCookie(tokenKeys.csrf);
	if (csrfToken) {
		config.headers = config.headers ?? {};
		config.headers[apiConfig.csrfHeaderName] = csrfToken;
	}

	return config;
});

// Refresh tokens are single-use, so concurrent 401s must share one refresh call.
let refreshInFlight: Promise<void> | null = null;

// Tabs share the auth cookies. Holding this lock makes them refresh one after another,
// so the next tab sends the token the previous one received instead of the rotated one.
const REFRESH_LOCK = "cognolith-auth-refresh";

async function postRefresh(): Promise<void> {
	try {
		await refreshClient.post(apiConfig.endpoints.refresh, {});
	} catch (error) {
		// 409: another tab refreshed with this token a moment ago and the shared cookies
		// already hold the new tokens (browsers without Web Locks, or a lost race)
		if (axios.isAxiosError(error) && error.response?.status === 409) return;
		throw error;
	}
}

function refreshSession(): Promise<void> {
	if (!refreshInFlight) {
		const locks = typeof navigator === "undefined" ? undefined : navigator.locks;
		const refresh: Promise<void> = locks
			? locks.request(REFRESH_LOCK, postRefresh).then(() => undefined)
			: postRefresh();
		refreshInFlight = refresh.finally(() => {
			refreshInFlight = null;
		});
	}
	return refreshInFlight;
}

apiClient.interceptors.response.use(
	(response) => response,
	async (error: AxiosError<ApiError>) => {
		const originalRequest = error.config as RequestWithRetry | undefined;

		// Handle token refresh on 401
		if (
			error.response?.status === 401 &&
			originalRequest &&
			!originalRequest._retry
		) {
			originalRequest._retry = true;

			const { clearAuth } = useAuthStore.getState();

			try {
				await refreshSession();

				return apiClient(originalRequest);
			} catch {
				clearAuth();
				return Promise.reject(new Error("Your session has expired."));
			}
		}

		// Handle transient failures with retry
		if (originalRequest && isRetryableError(error, originalRequest.method)) {
			// Don't retry if already attempted
			if (originalRequest._retry) {
				return Promise.reject(error);
			}

			originalRequest._retry = true;

			try {
				// Retry the request with exponential backoff
				return await retryWithExponentialBackoff(
					() => apiClient(originalRequest),
					{
						maxRetries: DEFAULT_RETRY_CONFIG.maxRetries,
						initialDelayMs: DEFAULT_RETRY_CONFIG.initialDelayMs,
						maxDelayMs: DEFAULT_RETRY_CONFIG.maxDelayMs,
						backoffMultiplier: DEFAULT_RETRY_CONFIG.backoffMultiplier,
					}
				);
			} catch (retryError) {
				// If all retries fail, return the original error
				return Promise.reject(retryError);
			}
		}

		const data = error.response?.data;
		const baseMessage = normalizeErrorMessage(
			data,
			error.message ?? "Something went wrong while contacting the server."
		);
		const message = data?.request_id
			? `${baseMessage} (Request ID: ${data.request_id})`
			: baseMessage;

		return Promise.reject(
			new APIRequestError(message, {
				statusCode: error.response?.status,
				errorCode: data?.error,
				requestId: data?.request_id,
				details: data?.details,
			})
		);
	}
);

export type OfflineReplayResult =
	| { status: "applied"; data: unknown }
	// The server copy changed since the write was queued; it was not applied
	| { status: "conflict" }
	| { status: "rejected"; statusCode: number };

type OfflineReplayListener = (request: QueuedRequest, result: OfflineReplayResult) => void;

const replayListeners = new Set<OfflineReplayListener>();

/** Be told how each replayed offline write ended, e.g. to refresh what it changed. */
export function onOfflineReplay(listener: OfflineReplayListener): () => void {
	replayListeners.add(listener);
	return () => replayListeners.delete(listener);
}

export async function processOfflineQueue(): Promise<{ succeeded: number; failed: number; conflicts: number }> {
	await requestQueue.ready();
	let succeeded = 0;
	let failed = 0;
	let conflicts = 0;

	await requestQueue.execute(async (req: QueuedRequest) => {
		let result: OfflineReplayResult;
		try {
			const response = await apiClient({
				method: req.method.toLowerCase(),
				url: req.url,
				data: req.data,
				params: req.params,
				offlineReplay: true,
			});
			succeeded++;
			result = { status: "applied", data: response.data };
		} catch (error) {
			const statusCode = error instanceof APIRequestError ? error.statusCode : undefined;
			// Offline again, or the server failing: keep it, and everything after it
			if (!statusCode || statusCode >= 500 || statusCode === 408 || statusCode === 429) return "retry";
			if (statusCode === 409) {
				conflicts++;
				result = { status: "conflict" };
			} else {
				failed++;
				result = { status: "rejected", statusCode };
			}
		}
		replayListeners.forEach((listener) => listener(req, result));
		return "done";
	});

	return { succeeded, failed, conflicts };
}
