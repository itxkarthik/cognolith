import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { tokenKeys } from "@/config/api";

import { config, proxy } from "../proxy";

function request(path: string, cookies: Record<string, string> = {}) {
  const cookie = Object.entries(cookies)
    .map(([name, value]) => `${name}=${value}`)
    .join("; ");
  return new NextRequest(`http://localhost${path}`, { headers: cookie ? { cookie } : {} });
}

describe("proxy", () => {
  it("sends a visitor with no session cookies to sign in", () => {
    const response = proxy(request("/dashboard/notes"));

    expect(response.headers.get("location")).toBe("http://localhost/auth/login?next=%2Fdashboard%2Fnotes");
  });

  it("lets a renewable session through to the dashboard", () => {
    const response = proxy(request("/dashboard", { [tokenKeys.refresh]: "r" }));

    expect(response.headers.get("location")).toBeNull();
  });

  it("does not run on the auth pages, so a revoked session's cookie can't bounce sign-in", () => {
    expect(config.matcher).toEqual(["/dashboard/:path*"]);
  });
});
