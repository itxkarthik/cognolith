import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { tokenKeys } from "@/config/api";

// Only the dashboard is guarded here. The auth pages are not redirected to the
// dashboard on cookie presence: a cookie can belong to a session revoked elsewhere,
// and bouncing on it loops between login and dashboard. The login page sends on
// users the app holds as signed in; a revoked session's first failed refresh clears
// that state along with the cookies.
export function proxy(request: NextRequest) {
  const accessToken = request.cookies.get(tokenKeys.access)?.value;
  // The access cookie expires after 30 minutes; a refresh cookie still means a
  // session the client can renew (AuthBootstrap's first 401 triggers the refresh).
  const refreshToken = request.cookies.get(tokenKeys.refresh)?.value;

  if (!accessToken && !refreshToken) {
    const loginUrl = new URL("/auth/login", request.url);
    loginUrl.searchParams.set("next", request.nextUrl.pathname);
    return NextResponse.redirect(loginUrl);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*"],
};
