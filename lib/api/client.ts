import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";

import { apiConfig, tokenKeys, getTimeoutForEndpoint } from "@/config/api";
import { useAuthStore } from "@/store/authStore";
import { isRetryableError, retryWithExponentialBackoff, DEFAULT_RETRY_CONFIG } from "@/lib/utils/retry";
import { requestQueue, type QueuedRequest } from "@/lib/utils/requestQueue";
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

function readCookie(name: string): string | null {
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

apiClient.interceptors.request.use((config) => {
	// Queue requests if offline (for POST, PUT, PATCH)
	const isOnline = typeof navigator !== "undefined" && navigator.onLine;
	const method = (config.method ?? "get").toUpperCase();

	if (!isOnline && ["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
		// Queue the request for later
		requestQueue.add(method, config.url || "", {
			data: config.data,
			params: config.params,
		});

		return Promise.reject(
			new APIRequestError("Request queued - you are currently offline", {
				statusCode: 0,
				errorCode: "OFFLINE",
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
				await refreshClient.post(apiConfig.endpoints.refresh, {});

				return apiClient(originalRequest);
			} catch {
				clearAuth();
				return Promise.reject(new Error("Your session has expired."));
			}
		}

		// Handle transient failures with retry
		if (originalRequest && isRetryableError(error)) {
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
		const baseMessage =
			data?.message ??
			data?.detail ??
			error.message ??
			"Something went wrong while contacting the server.";
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

export async function processOfflineQueue(): Promise<{ succeeded: number; failed: number }> {
	if (requestQueue.isEmpty()) {
		return { succeeded: 0, failed: 0 };
	}

	let succeeded = 0;
	let failed = 0;

	await requestQueue.execute(async (req: QueuedRequest) => {
		try {
			await apiClient({
				method: req.method.toLowerCase(),
				url: req.url,
				data: req.config.data,
				params: req.config.params,
			});
			succeeded++;
			return true;
		} catch {
			failed++;
			return false;
		}
	});

	return { succeeded, failed };
}
