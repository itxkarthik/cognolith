import { describe, it, expect } from "vitest";
import { getTimeoutForEndpoint } from "../api";

describe("API Configuration - Endpoint-Specific Timeouts", () => {
	describe("getTimeoutForEndpoint", () => {
		describe("File Upload Endpoints", () => {
			it("should return 120s for POST /documents/upload", () => {
				expect(getTimeoutForEndpoint("POST", "/api/v1/documents/upload")).toBe(120000);
			});

			it("should return 120s for POST /documents", () => {
				expect(getTimeoutForEndpoint("POST", "/api/v1/documents")).toBe(120000);
			});

			it("should return 120s for POST /documents with trailing slash", () => {
				expect(getTimeoutForEndpoint("POST", "/api/v1/documents/")).toBe(120000);
			});
		});

		describe("RAG and AI Operations", () => {
			it("should return 60s for POST /chat", () => {
				expect(getTimeoutForEndpoint("POST", "/api/v1/chat")).toBe(60000);
			});

			it("should return 60s for POST /chat with session ID", () => {
				expect(getTimeoutForEndpoint("POST", "/api/v1/chat/123/messages")).toBe(60000);
			});

			it("should return 60s for GET /search", () => {
				expect(getTimeoutForEndpoint("GET", "/api/v1/search")).toBe(60000);
			});

			it("should return 60s for GET /search with query params", () => {
				expect(getTimeoutForEndpoint("GET", "/api/v1/search?q=test")).toBe(60000);
			});

			it("should return 60s for POST /knowledge-graph", () => {
				expect(getTimeoutForEndpoint("POST", "/api/v1/knowledge-graph")).toBe(60000);
			});

			it("should return 60s for POST /rag", () => {
				expect(getTimeoutForEndpoint("POST", "/api/v1/rag")).toBe(60000);
			});
		});

		describe("Regular API Operations", () => {
			it("should return 15s for GET /documents", () => {
				expect(getTimeoutForEndpoint("GET", "/api/v1/documents")).toBe(15000);
			});

			it("should return 15s for GET /documents with ID", () => {
				expect(getTimeoutForEndpoint("GET", "/api/v1/documents/123")).toBe(15000);
			});

			it("should return 15s for GET /notes", () => {
				expect(getTimeoutForEndpoint("GET", "/api/v1/notes")).toBe(15000);
			});

			it("should return 15s for POST /notes", () => {
				expect(getTimeoutForEndpoint("POST", "/api/v1/notes")).toBe(15000);
			});

			it("should return 15s for GET /users", () => {
				expect(getTimeoutForEndpoint("GET", "/api/v1/users")).toBe(15000);
			});

			it("should return 15s for POST /auth", () => {
				expect(getTimeoutForEndpoint("POST", "/api/v1/auth/login")).toBe(15000);
			});
		});

		describe("Health Checks", () => {
			it("should return 5s for GET /health", () => {
				expect(getTimeoutForEndpoint("GET", "/api/v1/health")).toBe(5000);
			});

			it("should return 5s for /health with trailing slash", () => {
				expect(getTimeoutForEndpoint("GET", "/api/v1/health/")).toBe(5000);
			});
		});

		describe("Default Timeout", () => {
			it("should return 15s (default) for unknown endpoints", () => {
				expect(getTimeoutForEndpoint("GET", "/api/v1/unknown")).toBe(15000);
			});

			it("should return 15s for DELETE endpoints", () => {
				expect(getTimeoutForEndpoint("DELETE", "/api/v1/notes/123")).toBe(15000);
			});

			it("should return 15s for PATCH endpoints", () => {
				expect(getTimeoutForEndpoint("PATCH", "/api/v1/notes/123")).toBe(15000);
			});
		});

		describe("Case Insensitivity", () => {
			it("should handle lowercase HTTP methods", () => {
				expect(getTimeoutForEndpoint("post", "/api/v1/chat")).toBe(60000);
			});

    it("should handle mixed case paths", () => {
      expect(getTimeoutForEndpoint("POST", "/api/v1/Chat")).toBe(60000);
    });
		});

		describe("URL Normalization", () => {
			it("should handle URLs without base URL prefix", () => {
				expect(getTimeoutForEndpoint("GET", "/documents")).toBe(15000);
			});

			it("should handle URLs with query parameters", () => {
				expect(getTimeoutForEndpoint("GET", "/documents?limit=10&offset=0")).toBe(15000);
			});

			it("should handle URLs with fragments", () => {
				expect(getTimeoutForEndpoint("GET", "/documents#section")).toBe(15000);
			});

			it("should ignore multiple trailing slashes", () => {
				expect(getTimeoutForEndpoint("GET", "/documents///")).toBe(15000);
			});
		});

		describe("Prefix Matching", () => {
			it("should match POST /documents for POST /documents/123/edit", () => {
				expect(getTimeoutForEndpoint("POST", "/documents/123/edit")).toBe(120000);
			});

			it("should match GET /search for GET /search/advanced", () => {
				expect(getTimeoutForEndpoint("GET", "/search/advanced")).toBe(60000);
			});

			it("should match POST /rag for POST /rag/stream", () => {
				expect(getTimeoutForEndpoint("POST", "/rag/stream")).toBe(60000);
			});
		});
	});

	describe("Timeout Values", () => {
		it("should have health check as fastest timeout", () => {
			const timeouts = [
				getTimeoutForEndpoint("GET", "/health"),
				getTimeoutForEndpoint("GET", "/documents"),
				getTimeoutForEndpoint("POST", "/chat"),
				getTimeoutForEndpoint("POST", "/documents/upload"),
			];
			expect(Math.min(...timeouts)).toBe(5000);
		});

		it("should have file upload as slowest timeout", () => {
			const timeouts = [
				getTimeoutForEndpoint("GET", "/health"),
				getTimeoutForEndpoint("GET", "/documents"),
				getTimeoutForEndpoint("POST", "/chat"),
				getTimeoutForEndpoint("POST", "/documents/upload"),
			];
			expect(Math.max(...timeouts)).toBe(120000);
		});

		it("should maintain reasonable hierarchy", () => {
			const health = getTimeoutForEndpoint("GET", "/health");
			const regular = getTimeoutForEndpoint("GET", "/documents");
			const rag = getTimeoutForEndpoint("POST", "/chat");
			const upload = getTimeoutForEndpoint("POST", "/documents/upload");

			expect(health < regular).toBe(true);
			expect(regular < rag).toBe(true);
			expect(rag < upload).toBe(true);
		});
	});
});
