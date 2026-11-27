import axios, { type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { beforeEach, describe, expect, it } from "vitest";

// Both axios instances in the client copy the default adapter when created
let refreshStatus = 200;
let calls: string[] = [];
let resourceAuthorized = false;

const adapter: AxiosAdapter = async (config: InternalAxiosRequestConfig) => {
  const url = config.url ?? "";
  calls.push(url);
  const respond = (status: number) => {
    const response = { data: {}, status, statusText: String(status), headers: {}, config };
    if (status >= 400) throw Object.assign(new Error(`HTTP ${status}`), { isAxiosError: true, response, config });
    return response;
  };
  if (url.includes("refresh")) {
    // 409: the other tab's rotation has already put new cookies in the shared jar
    if (refreshStatus !== 401) resourceAuthorized = true;
    return respond(refreshStatus);
  }
  return respond(resourceAuthorized ? 200 : 401);
};
axios.defaults.adapter = adapter;

const { apiClient } = await import("../client");
const { useAuthStore } = await import("@/store/authStore");

describe("refresh racing another tab", () => {
  beforeEach(() => {
    calls = [];
    resourceAuthorized = false;
    useAuthStore.setState({ isAuthenticated: true, user: { id: 1 } as never });
  });

  it("treats 'already refreshed' as success and retries the request", async () => {
    refreshStatus = 409;

    const response = await apiClient.get("/notes/");

    expect(response.status).toBe(200);
    expect(calls.filter((url) => url === "/notes/")).toHaveLength(2);
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
  });

  it("still signs out when the refresh is refused", async () => {
    refreshStatus = 401;

    await expect(apiClient.get("/notes/")).rejects.toThrow("session has expired");
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });
});
