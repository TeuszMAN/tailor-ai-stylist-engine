from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.ratelimit import RateLimitRule, SlidingWindowRateLimiter

MEASUREMENTS = {"height_cm": 180, "weight_kg": 85, "chest_type": "medio", "belly_type": "medio"}


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_client(**overrides: object) -> Iterator[TestClient]:
    settings = Settings(llm_provider="none", _env_file=None, **overrides)  # type: ignore[arg-type]
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture()
def strict_client() -> Iterator[TestClient]:
    yield from make_client(rate_limit_per_minute=2, stylist_rate_limit_per_minute=1, max_request_bytes=2048)


def test_sliding_window_blocks_then_recovers() -> None:
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter(clock=clock)
    rule = RateLimitRule("t", limit=2, window_seconds=60)
    assert limiter.hit("ip", rule).remaining == 1
    assert limiter.hit("ip", rule).remaining == 0
    blocked = limiter.hit("ip", rule)
    assert not blocked.allowed and blocked.retry_after_seconds == 60
    assert limiter.hit("other-ip", rule).allowed  # keys are independent
    clock.now += 61
    assert limiter.hit("ip", rule).allowed


def test_zero_budget_is_never_allowed() -> None:
    decision = SlidingWindowRateLimiter().hit("k", RateLimitRule("t", limit=0))
    assert not decision.allowed and decision.retry_after_seconds == 60


def test_limiter_evicts_stale_keys() -> None:
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter(clock=clock, max_keys=3)
    rule = RateLimitRule("t", limit=5, window_seconds=10)
    for index in range(3):
        limiter.hit(f"ip-{index}", rule)
    clock.now += 11
    limiter.hit("ip-new-1", rule)
    limiter.hit("ip-new-2", rule)
    assert limiter.tracked_keys <= 3


def test_api_bucket_returns_429_with_retry_after(strict_client: TestClient) -> None:
    first = strict_client.post("/api/v1/fit-finder", json=MEASUREMENTS)
    assert first.status_code == 200
    assert first.headers["x-ratelimit-limit"] == "2"
    assert first.headers["x-ratelimit-remaining"] == "1"
    assert strict_client.post("/api/v1/fit-finder", json=MEASUREMENTS).status_code == 200
    blocked = strict_client.post("/api/v1/fit-finder", json=MEASUREMENTS)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert "Muitas requisições" in blocked.json()["detail"]


def test_stylist_has_its_own_stricter_bucket(strict_client: TestClient) -> None:
    assert strict_client.post("/api/v1/stylist/recommend", json={"message": "Entrevista"}).status_code == 200
    assert strict_client.post("/api/v1/stylist/recommend", json={"message": "Entrevista"}).status_code == 429
    assert strict_client.post("/api/v1/fit-finder", json=MEASUREMENTS).status_code == 200


def test_health_and_docs_are_not_limited(strict_client: TestClient) -> None:
    for _ in range(5):
        assert strict_client.get("/health").status_code == 200
    assert strict_client.get("/openapi.json").status_code == 200


def test_rate_limit_can_be_disabled() -> None:
    for client in make_client(rate_limit_enabled=False, rate_limit_per_minute=1):
        for _ in range(3):
            assert client.post("/api/v1/fit-finder", json=MEASUREMENTS).status_code == 200


def test_oversized_body_is_rejected(strict_client: TestClient) -> None:
    response = strict_client.post(
        "/api/v1/stylist/recommend",
        content=b'{"message": "' + b"a" * 4096 + b'"}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413


def test_cors_defaults_to_the_local_storefront_only() -> None:
    for client in make_client():
        allowed = client.options(
            "/api/v1/stylist/recommend",
            headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
        )
        assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"
        denied = client.options(
            "/api/v1/stylist/recommend",
            headers={"Origin": "https://attacker.example", "Access-Control-Request-Method": "POST"},
        )
        assert "access-control-allow-origin" not in denied.headers


def test_rate_limited_responses_keep_cors_headers() -> None:
    for client in make_client(rate_limit_per_minute=1):
        origin = {"Origin": "http://localhost:3000"}
        client.post("/api/v1/fit-finder", json=MEASUREMENTS, headers=origin)
        blocked = client.post("/api/v1/fit-finder", json=MEASUREMENTS, headers=origin)
        assert blocked.status_code == 429
        assert blocked.headers.get("access-control-allow-origin") == "http://localhost:3000"
        assert "retry-after" in blocked.headers.get("access-control-expose-headers", "").lower()
