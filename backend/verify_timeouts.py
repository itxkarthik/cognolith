import asyncio
import io
from urllib.parse import urljoin

import httpx

BASE_URL = "http://localhost:8000"
API_V1_STR = "/api/v1"


async def test_slow():
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.get(urljoin(BASE_URL, f"{API_V1_STR}/test/slow?delay_seconds=5"))
            return r.status_code == 200
        except Exception as e:
            print(f"Slow endpoint failed: {e}")
            return False


async def test_upload():
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            data = b"X" * (5 * 1024 * 1024)
            files = {"file": ("test.bin", io.BytesIO(data))}
            r = await client.post(urljoin(BASE_URL, f"{API_V1_STR}/test/upload-large"), files=files)
            return r.status_code == 200
        except Exception as e:
            print(f"Upload endpoint failed: {e}")
            return False


async def test_rag():
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            r = await client.post(
                urljoin(BASE_URL, f"{API_V1_STR}/test/rag-slow?query=test&delay_seconds=10")
            )
            return r.status_code == 200
        except Exception as e:
            print(f"RAG endpoint failed: {e}")
            return False


async def main():
    print("Testing timeout configuration...")
    results = [
        ("Slow endpoint", await test_slow()),
        ("File upload", await test_upload()),
        ("RAG query", await test_rag()),
    ]

    for name, passed in results:
        print(f"{'✓' if passed else '✗'} {name}")

    return all(p for _, p in results)


if __name__ == "__main__":
    import sys

    success = asyncio.run(main())
    sys.exit(0 if success else 1)
