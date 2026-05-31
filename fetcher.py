"""Optional HTTP fetch (often blocked). Browser mode is recommended."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from parser import RestaurantRecord, parse_restaurant, validate_tripadvisor_url

ALLOWED_DOMAIN = "tripadvisor.com"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass
class FetchResult:
    url: str
    status_code: int
    restaurant: RestaurantRecord | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "status_code": self.status_code,
            "restaurant": self.restaurant.to_dict() if self.restaurant else None,
            "error": self.error,
        }


def fetch_tripadvisor(url: str, timeout: float = 30.0) -> FetchResult:
    safe_url = validate_tripadvisor_url(url)
    try:
        with httpx.Client(
            headers=DEFAULT_HEADERS, follow_redirects=True, timeout=timeout
        ) as client:
            response = client.get(safe_url)
            final_url = str(response.url)
            if ALLOWED_DOMAIN not in urlparse(final_url).netloc.lower():
                return FetchResult(
                    url=final_url,
                    status_code=response.status_code,
                    error="Redirect left Tripadvisor",
                )
            blocked = response.status_code == 403
            record = parse_restaurant(
                response.text, final_url, blocked=blocked
            )
            return FetchResult(
                url=final_url,
                status_code=response.status_code,
                restaurant=record,
                error=None if response.is_success else f"HTTP {response.status_code}",
            )
    except httpx.HTTPError as exc:
        return FetchResult(url=safe_url, status_code=0, error=str(exc))
