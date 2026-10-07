"""A lightweight in-memory rate limiter for sensitive POST endpoints.

Keeps a sliding window per client IP for auth and upload paths. For a single
process deployment this is adequate; swap for a cache/Redis backend at scale.
"""
import time
from collections import defaultdict, deque

from django.http import HttpResponse

_WINDOW = 60  # seconds
_LIMITS = {
    "/accounts/login": 10,
    "/accounts/register": 6,
    "/orders/proof": 20,
}
_HITS = defaultdict(deque)


class SimpleRateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "POST":
            path = request.path
            limit = None
            for prefix, lim in _LIMITS.items():
                if path.startswith(prefix):
                    limit = lim
                    break
            if limit is not None:
                ip = self._client_ip(request)
                key = f"{ip}:{prefix}"
                now = time.time()
                bucket = _HITS[key]
                while bucket and bucket[0] < now - _WINDOW:
                    bucket.popleft()
                if len(bucket) >= limit:
                    return HttpResponse(
                        "Too many requests. Please slow down and try again shortly.",
                        status=429,
                    )
                bucket.append(now)
        return self.get_response(request)

    @staticmethod
    def _client_ip(request):
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "unknown")
