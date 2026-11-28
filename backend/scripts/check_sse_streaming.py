"""
Check that chat replies stream token by token through the deployed stack.

    python -m scripts.check_sse_streaming --base-url https://cognolith.example.com --email you@example.com

Signs in, streams one short reply through the given URL (the same path a browser
uses) into a chat session titled "SSE streaming check", reused across runs, and
reports when each event arrived. A proxy that buffers the stream shows every token
arriving at once; a working stack shows them spread over the generation time.

Outside local development the session cookies are Secure, so the URL must be HTTPS
(or loopback, in local development).
--internal is for a URL on the private Compose network (http://frontend:3000, as the
release smoke tests use): the cookies are sent over its plain HTTP, which never
leaves the host.

The password is read from SSE_CHECK_PASSWORD, else prompted for. Exit status: 0
streaming, 1 buffered or inconclusive, 2 the request failed.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
import time

import httpx

CSRF_COOKIE = "csrf-token"
CSRF_HEADER = "X-CSRF-Token"
QUESTION = "Reply with a sentence of about twenty words about the ocean."
SESSION_TITLE = "SSE streaming check"
PASSWORD_ENV = "SSE_CHECK_PASSWORD"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check token-by-token SSE streaming.")
    parser.add_argument(
        "--base-url", required=True, help="Frontend URL, e.g. https://cognolith.example.com"
    )
    parser.add_argument("--email", required=True)
    parser.add_argument(
        "--internal",
        action="store_true",
        help="The URL is on the private Compose network: send Secure cookies over its plain HTTP",
    )
    return parser.parse_args()


# Plain HTTP that stays on this machine, as in local development
_LOOPBACK = {"localhost", "127.0.0.1", "::1"}


_SECURE_ATTRIBUTE = re.compile(r";\s*secure\s*(?=;|$)", re.IGNORECASE)


class _CookiesOverPlainHttp(httpx.BaseTransport):
    """
    Drops the Secure attribute from the cookies a private network URL sets, so the
    client sends them back over its plain HTTP. (httpx copies its cookie jar per
    request, so a cookie policy wouldn't last.)
    """

    def __init__(self, transport: httpx.BaseTransport) -> None:
        self._transport = transport

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self._transport.handle_request(request)
        headers = [
            (name, _SECURE_ATTRIBUTE.sub("", value) if name == "set-cookie" else value)
            for name, value in response.headers.multi_items()
        ]
        return httpx.Response(
            response.status_code,
            headers=headers,
            stream=response.stream,
            extensions=response.extensions,
            request=request,
        )

    def close(self) -> None:
        self._transport.close()


def make_client(
    base_url: str,
    *,
    internal: bool,
    timeout: float = 30,
    transport: httpx.BaseTransport | None = None,
) -> httpx.Client:
    url = httpx.URL(base_url)
    if url.scheme == "http" and not internal and url.host not in _LOOPBACK:
        # Secure session cookies wouldn't be sent, and a password shouldn't be either
        raise ValueError("Use an HTTPS URL, or --internal for one on the Compose network")
    if internal:
        transport = _CookiesOverPlainHttp(transport or httpx.HTTPTransport())
        # The origin is the Compose hostname: send none, like any non-browser client
        headers = {}
    else:
        # The auth endpoints refuse cross-site requests: present the site's own origin
        headers = {"Origin": base_url}
    return httpx.Client(base_url=base_url, headers=headers, timeout=timeout, transport=transport)


def _check_session(client: httpx.Client, csrf: dict[str, str]) -> int:
    listed = client.get("/api/v1/chat/sessions", params={"limit": 100})
    listed.raise_for_status()
    for chat in listed.json()["data"]:
        if chat["title"] == SESSION_TITLE:
            return chat["id"]
    created = client.post("/api/v1/chat/sessions", json={"title": SESSION_TITLE}, headers=csrf)
    created.raise_for_status()
    return created.json()["id"]


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    try:
        client = make_client(base_url, internal=args.internal, timeout=30)
    except ValueError as error:
        print(error)
        return 2
    password = os.environ.get(PASSWORD_ENV) or getpass.getpass("Password: ")
    with client:
        client.get("/api/v1/csrf-token").raise_for_status()
        login = client.post(
            "/api/v1/login/access-token", data={"username": args.email, "password": password}
        )
        if login.status_code != 200:
            print(f"Sign-in failed: HTTP {login.status_code} {login.text[:200]}")
            return 2
        csrf = {CSRF_HEADER: client.cookies.get(CSRF_COOKIE) or ""}

        session_id = _check_session(client, csrf)

        started = time.perf_counter()
        token_times: list[float] = []
        events = 0
        with client.stream(
            "POST",
            f"/api/v1/chat/sessions/{session_id}/messages/stream",
            json={"content": QUESTION, "role": "user"},
            headers={**csrf, "Accept": "text/event-stream"},
            timeout=httpx.Timeout(30, read=300),
        ) as response:
            print(
                f"HTTP {response.status_code}; content-encoding={response.headers.get('content-encoding')}; "
                f"cache-control={response.headers.get('cache-control')}"
            )
            if response.status_code != 200:
                print(response.read().decode(errors="replace")[:300])
                return 2
            for line in response.iter_lines():
                if line.startswith("event:"):
                    events += 1
                    if line.strip() == "event: token":
                        token_times.append(time.perf_counter() - started)

    print(
        f"events={events} token_events={len(token_times)} total={time.perf_counter() - started:.1f}s"
    )
    if len(token_times) < 3:
        print("INCONCLUSIVE: too few tokens to judge (is the chat model available?)")
        return 1
    spread = token_times[-1] - token_times[0]
    print(
        f"first token at {token_times[0]:.2f}s, last at {token_times[-1]:.2f}s (spread {spread:.2f}s)"
    )
    if spread < 0.05:
        print("BUFFERED: every token arrived at once; a proxy is holding the stream")
        return 1
    print("STREAMING: tokens arrived incrementally")
    return 0


if __name__ == "__main__":
    sys.exit(main())
