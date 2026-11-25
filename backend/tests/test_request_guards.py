"""Body-size, CSRF-rotation and cross-site checks, exercised on minimal apps."""

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.csrf import CSRFMiddleware
from app.core.middleware import MaxRequestBodySizeMiddleware


def _body_limited_client(limit: int) -> TestClient:
    app = FastAPI()

    @app.post("/echo")
    async def echo(request: Request) -> dict[str, int]:
        return {"size": len(await request.body())}

    @app.post("/upload")
    async def upload(file: UploadFile = File(...)) -> dict[str, int]:
        return {"size": len(await file.read())}

    app.add_middleware(MaxRequestBodySizeMiddleware, max_body_size=limit)
    return TestClient(app)


def test_declared_oversized_body_is_rejected() -> None:
    client = _body_limited_client(10)

    response = client.post("/echo", content=b"x" * 11)

    assert response.status_code == 413


def test_chunked_body_without_content_length_is_capped() -> None:
    client = _body_limited_client(10)

    def chunks():
        for _ in range(5):
            yield b"x" * 5

    response = client.post("/echo", content=chunks())

    assert response.status_code == 413


def test_chunked_multipart_upload_is_capped_not_reported_as_parse_error() -> None:
    client = _body_limited_client(100)
    body = (
        b"--b\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.txt\"\r\n"
        b"Content-Type: text/plain\r\n\r\n" + b"x" * 500 + b"\r\n--b--\r\n"
    )

    def chunks():
        for start in range(0, len(body), 50):
            yield body[start : start + 50]

    response = client.post(
        "/upload",
        content=chunks(),
        headers={"Content-Type": "multipart/form-data; boundary=b"},
    )

    assert response.status_code == 413


def test_small_body_passes() -> None:
    client = _body_limited_client(10)

    response = client.post("/echo", content=b"x" * 10)

    assert response.status_code == 200
    assert response.json() == {"size": 10}


def test_malformed_content_length_is_a_client_error() -> None:
    client = _body_limited_client(10)

    response = client.post("/echo", content=b"x", headers={"Content-Length": "abc"})

    assert response.status_code == 400


def _csrf_client() -> TestClient:
    app = FastAPI()

    @app.get("/api/v1/items")
    def list_items() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/v1/items")
    def create_item() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/v1/login/access-token")
    def login() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(CSRFMiddleware)
    return TestClient(app)


def test_csrf_cookie_is_not_rotated_once_issued() -> None:
    client = _csrf_client()

    first = client.get("/api/v1/items")
    token = first.cookies.get(settings.CSRF_COOKIE_NAME)
    assert token

    second = client.get("/api/v1/items")
    write = client.post("/api/v1/items", headers={settings.CSRF_HEADER_NAME: token})

    assert settings.CSRF_COOKIE_NAME not in second.cookies
    assert write.status_code == 200
    assert settings.CSRF_COOKIE_NAME not in write.cookies
    # The same token keeps working for parallel and later requests
    again = client.post("/api/v1/items", headers={settings.CSRF_HEADER_NAME: token})
    assert again.status_code == 200


def test_cross_site_login_post_is_refused() -> None:
    client = _csrf_client()

    response = client.post(
        "/api/v1/login/access-token", headers={"Origin": "https://evil.example"}
    )

    assert response.status_code == 403


def test_cross_site_fetch_metadata_is_refused_without_origin() -> None:
    client = _csrf_client()

    response = client.post(
        "/api/v1/login/access-token", headers={"Sec-Fetch-Site": "cross-site"}
    )

    assert response.status_code == 403


def test_same_origin_and_non_browser_login_posts_are_allowed() -> None:
    client = _csrf_client()

    from_frontend = client.post(
        "/api/v1/login/access-token", headers={"Origin": settings.FRONTEND_HOST}
    )
    without_browser_headers = client.post("/api/v1/login/access-token")

    assert from_frontend.status_code == 200
    assert without_browser_headers.status_code == 200
