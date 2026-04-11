import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";

import { apiConfig, tokenKeys, getTimeoutForEndpoint } from "@/config/api";
import { useAuthStore } from "@/store/authStore";
import { isRetryableError, retryWithExponentialBackoff, DEFAULT_RETRY_CONFIG } from "@/lib/utils/retry";

type RequestWithRetry = InternalAxiosRequestConfig & {
	_retry?: boolean;
};

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

	const method = (config.method ?? "get").toUpperCase();
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
	async (error: AxiosError<{ detail?: string; message?: string }>) => {
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

		const message =
			error.response?.data?.detail ??
			error.response?.data?.message ??
			error.message ??
			"Something went wrong while contacting the server.";

		return Promise.reject(new Error(message));
	}
);
