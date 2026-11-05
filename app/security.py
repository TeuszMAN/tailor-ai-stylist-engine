"""HTTP guards for a publicly exposed engine: request size limit and per-client rate limiting.

* `413` when `Content-Length` exceeds `MAX_REQUEST_BYTES`.
* `429` (+ `Retry-After`) per client IP and bucket: the stylist endpoint (may call an LLM)
  has its own, stricter bucket. `/health`, `/docs` and `/openapi.json` are not limited.

Behind a reverse proxy, run uvicorn with `--proxy-headers` and set `FORWARDED_ALLOW_IPS` so
`request.client.host` is the real client IP.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.ratelimit import RateLimitRule, SlidingWindowRateLimiter

STYLIST_PATH = "/api/v1/stylist/recommend"
API_PREFIX = "/api/"
BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})


class HttpGuards:
    def __init__(
        self,
        *,
        enabled: bool,
        default_per_minute: int,
        stylist_per_minute: int,
        max_request_bytes: int,
        limiter: SlidingWindowRateLimiter | None = None,
    ) -> None:
        self.enabled = enabled
        self.max_request_bytes = max_request_bytes
        self.limiter = limiter or SlidingWindowRateLimiter()
        self.default_rule = RateLimitRule("api", default_per_minute)
        self.stylist_rule = RateLimitRule("stylist", stylist_per_minute)

    def rule_for(self, path: str) -> RateLimitRule | None:
        if path == STYLIST_PATH:
            return self.stylist_rule
        if path.startswith(API_PREFIX):
            return self.default_rule
        return None

    @staticmethod
    def client_key(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    def too_large(self, request: Request) -> bool:
        if request.method not in BODY_METHODS:
            return False
        length = request.headers.get("content-length", "")
        return length.isdigit() and int(length) > self.max_request_bytes

    async def __call__(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if self.too_large(request):
            return JSONResponse(
                status_code=413,
                content={"detail": f"Requisição maior que o limite de {self.max_request_bytes} bytes."},
            )
        rule = self.rule_for(request.url.path) if self.enabled and request.method != "OPTIONS" else None
        if rule is None:
            return await call_next(request)

        decision = self.limiter.hit(f"{rule.name}:{self.client_key(request)}", rule)
        headers = {"X-RateLimit-Limit": str(decision.limit), "X-RateLimit-Remaining": str(decision.remaining)}
        if not decision.allowed:
            headers["Retry-After"] = str(decision.retry_after_seconds)
            return JSONResponse(
                status_code=429,
                content={"detail": "Muitas requisições. Tente novamente em instantes."},
                headers=headers,
            )
        response = await call_next(request)
        response.headers.update(headers)
        return response


def install_http_guards(app: FastAPI, guards: HttpGuards) -> None:
    """Register the guards as HTTP middleware (call before adding CORS so CORS stays outermost)."""
    app.middleware("http")(guards)
