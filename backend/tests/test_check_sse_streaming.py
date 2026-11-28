"""The release smoke test's SSE check signs in over the right URLs (issue #28)."""

import httpx
import pytest

from scripts.check_sse_streaming import make_client


def _server(seen: list[str | None]) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login":
            # Outside local development the session cookies are Secure
            return httpx.Response(
                200, headers={"set-cookie": "access_token=abc; Path=/; Secure; HttpOnly; SameSite=lax"}
            )
        seen.append(request.headers.get("cookie"))
        return httpx.Response(200)

    return httpx.MockTransport(handle)


def test_internal_mode_sends_secure_cookies_over_the_compose_network() -> None:
    seen: list[str | None] = []
    with make_client("http://frontend:3000", internal=True, transport=_server(seen)) as client:
        client.post("/login")
        client.get("/api/v1/chat/sessions")

    assert seen == ["access_token=abc"]
    # Not a browser: no Origin with the Compose hostname
    assert "origin" not in client.headers


def test_a_plain_http_url_elsewhere_is_refused() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        make_client("http://cognolith.example.com", internal=False)


@pytest.mark.parametrize("url", ["https://cognolith.example.com", "http://localhost:8080"])
def test_https_and_loopback_urls_are_allowed(url: str) -> None:
    with make_client(url, internal=False) as client:
        assert client.headers["origin"] == url
