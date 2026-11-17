"""Shared HTTP client. Tests replace `transport` with an httpx.MockTransport."""
import httpx

transport: httpx.BaseTransport | None = None


def client() -> httpx.Client:
    return httpx.Client(timeout=20, transport=transport, follow_redirects=True)
