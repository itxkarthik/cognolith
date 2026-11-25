"""
Check that chat replies stream token by token through the deployed stack.

    python -m scripts.check_sse_streaming --base-url https://cognolith.example.com --email you@example.com

Signs in, opens a chat session titled "SSE streaming check", streams one short
reply through the public URL (the same path a browser uses) and reports when
each event arrived. A proxy that buffers the stream shows every token arriving
at once; a working stack shows them spread over the generation time.
"""

from __future__ import annotations

import argparse
import getpass
import sys
import time

import httpx

CSRF_COOKIE = "csrf-token"
CSRF_HEADER = "X-CSRF-Token"
QUESTION = "Reply with a sentence of about twenty words about the ocean."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check token-by-token SSE streaming.")
    parser.add_argument("--base-url", required=True, help="Public frontend URL, e.g. http://localhost:8080")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", help="Prompted for when omitted")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    password = args.password or getpass.getpass("Password: ")
    # The auth endpoints refuse cross-site requests, so present the site's own origin
    with httpx.Client(base_url=base_url, headers={"Origin": base_url}, timeout=30) as client:
        client.get("/api/v1/csrf-token").raise_for_status()
        login = client.post(
            "/api/v1/login/access-token", data={"username": args.email, "password": password}
        )
        if login.status_code != 200:
            print(f"Sign-in failed: HTTP {login.status_code} {login.text[:200]}")
            return 2
        csrf = {CSRF_HEADER: client.cookies.get(CSRF_COOKIE) or ""}

        created = client.post("/api/v1/chat/sessions", json={"title": "SSE streaming check"}, headers=csrf)
        created.raise_for_status()
        session_id = created.json()["id"]

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

    print(f"events={events} token_events={len(token_times)} total={time.perf_counter() - started:.1f}s")
    if len(token_times) < 3:
        print("INCONCLUSIVE: too few tokens to judge (is the chat model available?)")
        return 1
    spread = token_times[-1] - token_times[0]
    print(f"first token at {token_times[0]:.2f}s, last at {token_times[-1]:.2f}s (spread {spread:.2f}s)")
    if spread < 0.05:
        print("BUFFERED: every token arrived at once; a proxy is holding the stream")
        return 1
    print("STREAMING: tokens arrived incrementally")
    return 0


if __name__ == "__main__":
    sys.exit(main())
