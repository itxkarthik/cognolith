const API_BASE_URL =
	process.env.NEXT_PUBLIC_API_URL ?? "/api/v1";

// Endpoint-specific timeout configurations (in milliseconds)
// Different operations need different timeout durations based on expected processing time
const ENDPOINT_TIMEOUTS = {
	// File upload endpoints - allow longer timeout for large files
	"POST /documents/upload": 120000, // 120 seconds for large file uploads
	"POST /documents": 120000,

	// RAG and search operations - AI processing takes time
	"POST /chat": 60000, // Bound local model requests; failed sends are explicitly retryable by the user
	"GET /search": 60000, // 60 seconds for semantic search
	"POST /knowledge-graph": 60000, // 60 seconds for graph generation
	"POST /rag": 60000, // 60 seconds for RAG queries

	// Regular API operations - standard timeout
	"GET /documents": 15000, // 15 seconds
	"GET /notes": 15000, // 15 seconds
	"POST /notes": 15000, // 15 seconds
	"GET /users": 15000, // 15 seconds
	"POST /auth": 15000, // 15 seconds
	"GET /health": 5000, // 5 seconds for health checks
} as const;

export const apiConfig = {
	baseUrl: API_BASE_URL,
	timeoutMs: 15000, // Default timeout
	csrfHeaderName: "X-CSRF-Token",
	endpointTimeouts: ENDPOINT_TIMEOUTS,
	endpoints: {
		login: "/login/access-token",
		register: "/users/signup",
		refresh: "/auth/refresh",
		me: "/users/me",
		logout: "/auth/logout",
	},
};

/**
 * Get the appropriate timeout for a given HTTP method and URL path
 * Matches patterns like "POST /documents/upload" or "GET /search"
 */
export function getTimeoutForEndpoint(method: string, url: string): number {
	// Normalize URL to just the path portion
	const path = url.replace(apiConfig.baseUrl, "").split("?")[0].toLowerCase();

	// Try to find a matching pattern
	for (const [pattern, timeout] of Object.entries(ENDPOINT_TIMEOUTS)) {
		const [patternMethod, patternPath] = pattern.split(" ");

		// Support both exact matches and prefix matches
		if (
			method.toUpperCase() === patternMethod &&
			(path === patternPath || path.startsWith(patternPath + "/"))
		) {
			return timeout;
		}
	}

	// Return default timeout if no specific pattern matched
	return apiConfig.timeoutMs;
}

export const tokenKeys = {
	access: "auth-access-token",
	refresh: "auth-refresh-token",
	csrf: "csrf-token",
};
