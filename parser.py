"""Extract name, email, image, phone from any Tripadvisor page."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

ALLOWED_DOMAIN = "tripadvisor.com"
RESTAURANT_PATH = "Restaurant_Review"

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{2,4}[-.\s]?\d{2,4}[-.\s]?\d{0,4}"
)


@dataclass
class RestaurantRecord:
    url: str
    captured_at: str
    name: str | None = None
    email: str | None = None
    image_url: str | None = None
    phone: str | None = None
    skipped: bool = False
    skip_reason: str | None = None
    blocked: bool = False

    def has_data(self) -> bool:
        return bool(self.name or self.email or self.image_url or self.phone)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "captured_at": self.captured_at,
            "name": self.name,
            "email": self.email,
            "image_url": self.image_url,
            "phone": self.phone,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "blocked": self.blocked,
        }


def is_tripadvisor_url(url: str) -> bool:
    return ALLOWED_DOMAIN in urlparse(url).netloc.lower()


def is_restaurant_page(url: str) -> bool:
    return RESTAURANT_PATH in url


def validate_tripadvisor_url(url: str) -> str:
    url = url.strip()
    if not url:
        raise ValueError("URL is required")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if not is_tripadvisor_url(url):
        raise ValueError(f"Only {ALLOWED_DOMAIN} is allowed")
    return url


def _parse_json_ld(soup: BeautifulSoup) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for tag in soup.find_all("script", type="application/ld+json"):
        if not tag.string:
            continue
        try:
            data = json.loads(tag.string)
            if isinstance(data, list):
                items.extend(x for x in data if isinstance(x, dict))
            elif isinstance(data, dict):
                items.append(data)
        except json.JSONDecodeError:
            continue
    return items


def _first_image(val: Any) -> str | None:
    if isinstance(val, str) and val.startswith("http"):
        return val
    if isinstance(val, dict) and val.get("url"):
        return str(val["url"])
    if isinstance(val, list):
        for item in val:
            url = _first_image(item)
            if url:
                return url
    return None


def _clean_name(raw: str | None) -> str | None:
    if not raw:
        return None
    name = raw.strip()
    for sep in (
        " - Tripadvisor",
        " | Tripadvisor",
        " - TripAdvisor",
        " | TripAdvisor",
    ):
        if sep in name:
            name = name.split(sep)[0].strip()
    return name or None


def _normalize_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    phone = raw.strip()
    if phone.startswith("tel:"):
        phone = phone[4:]
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 7:
        return None
    return phone


def _extract_from_json_ld(blocks: list[dict[str, Any]]) -> dict[str, str | None]:
    out: dict[str, str | None] = {
        "name": None,
        "email": None,
        "image_url": None,
        "phone": None,
    }
    for item in blocks:
        if not item.get("name") and not item.get("telephone") and not item.get("email"):
            continue
        out["name"] = out["name"] or item.get("name")
        out["phone"] = out["phone"] or _normalize_phone(item.get("telephone"))
        out["email"] = out["email"] or item.get("email")
        out["image_url"] = out["image_url"] or _first_image(item.get("image"))
    return out


def _extract_mailto_tel(soup: BeautifulSoup) -> dict[str, str | None]:
    email = None
    phone = None
    for a in soup.find_all("a", href=True):
        href = str(a["href"]).strip()
        if href.startswith("mailto:") and not email:
            email = href[7:].split("?")[0].strip() or None
        if href.startswith("tel:") and not phone:
            phone = _normalize_phone(href)
    return {"email": email, "phone": phone}


def _extract_meta(soup: BeautifulSoup) -> dict[str, str | None]:
    meta: dict[str, str] = {}
    for tag in soup.find_all("meta"):
        key = tag.get("property") or tag.get("name")
        content = tag.get("content")
        if key and content:
            meta[str(key)] = str(content)
    name = _clean_name(meta.get("og:title") or meta.get("twitter:title"))
    image = meta.get("og:image") or meta.get("twitter:image")
    return {"name": name, "image_url": image}


def _extract_h1_name(soup: BeautifulSoup) -> str | None:
    for tag in soup.find_all("h1"):
        text = _clean_name(tag.get_text(strip=True))
        if text and len(text) > 2:
            return text
    return None


def _extract_emails_text(soup: BeautifulSoup) -> str | None:
    for match in EMAIL_RE.findall(soup.get_text(" ", strip=True)[:80000]):
        lower = match.lower()
        if "tripadvisor" in lower or "example.com" in lower:
            continue
        return match
    return None


def _extract_from_raw_html(html: str) -> dict[str, str | None]:
    """Tripadvisor embeds data in script blobs — quick regex fallback."""
    out: dict[str, str | None] = {"name": None, "phone": None, "image_url": None}
    m = re.search(r'"name"\s*:\s*"([^"]{2,200})"', html)
    if m:
        out["name"] = _clean_name(m.group(1).replace("\\u0026", "&"))
    m = re.search(r'"telephone"\s*:\s*"([^"]+)"', html)
    if m:
        out["phone"] = _normalize_phone(m.group(1))
    m = re.search(r'"image"\s*:\s*"(https?://[^"]+)"', html)
    if m:
        out["image_url"] = m.group(1)
    m = re.search(r'"imageUrl"\s*:\s*"(https?://[^"]+)"', html)
    if m:
        out["image_url"] = out["image_url"] or m.group(1)
    return out


def parse_place_detail(html: str, url: str, *, blocked: bool = False) -> RestaurantRecord:
    """Extract 4 fields from the current page (restaurant, tour, attraction, etc.)."""
    captured_at = datetime.now(timezone.utc).isoformat()

    if blocked:
        return RestaurantRecord(
            url=url,
            captured_at=captured_at,
            blocked=True,
            skip_reason="Tripadvisor blocked this page",
        )

    soup = BeautifulSoup(html, "html.parser")
    json_ld = _parse_json_ld(soup)
    ld = _extract_from_json_ld(json_ld)
    links = _extract_mailto_tel(soup)
    meta = _extract_meta(soup)
    raw = _extract_from_raw_html(html[:500000])

    name = _clean_name(ld["name"]) or _extract_h1_name(soup) or meta["name"] or raw["name"]
    email = ld["email"] or links["email"] or _extract_emails_text(soup)
    phone = ld["phone"] or links["phone"] or raw["phone"]
    image_url = ld["image_url"] or meta["image_url"] or raw["image_url"]

    if not phone:
        text = soup.get_text(" ", strip=True)[:40000]
        for match in PHONE_RE.findall(text):
            norm = _normalize_phone(match)
            if norm and len(re.sub(r"\D", "", norm)) >= 9:
                phone = norm
                break

    if not image_url:
        for img in soup.find_all("img"):
            src = str(img.get("src") or img.get("data-src") or "")
            if src.startswith("http") and (
                "media-cdn" in src
                or "dynamic-media" in src
                or "photo" in src.lower()
            ):
                image_url = src
                break

    return RestaurantRecord(
        url=url.split("?")[0],
        captured_at=captured_at,
        name=name,
        email=email,
        image_url=image_url,
        phone=phone,
    )


def _restaurant_review_url(href: str, base_url: str) -> str | None:
    if RESTAURANT_PATH not in href:
        return None
    full = urljoin(base_url, href.split("#")[0])
    if not is_tripadvisor_url(full):
        return None
    return full.split("?")[0]


def _card_image(anchor: Any) -> str | None:
    for parent in (anchor, anchor.parent, anchor.find_parent(["div", "article", "li"])):
        if not parent:
            continue
        img = parent.find("img") if hasattr(parent, "find") else None
        if img:
            src = str(img.get("src") or img.get("data-src") or "")
            if src.startswith("http"):
                return src
    return None


def parse_listing_page(html: str, page_url: str) -> list[RestaurantRecord]:
    soup = BeautifulSoup(html, "html.parser")
    captured_at = datetime.now(timezone.utc).isoformat()
    seen_urls: set[str] = set()
    records: list[RestaurantRecord] = []

    for a in soup.find_all("a", href=True):
        full = _restaurant_review_url(str(a["href"]), page_url)
        if not full or full in seen_urls:
            continue
        seen_urls.add(full)

        label = " ".join(a.get_text(strip=True).split())
        aria = a.get("aria-label")
        name = _clean_name(label) or _clean_name(str(aria) if aria else None)
        if not name or len(name) < 2:
            parent = a.find_parent(["div", "article", "section"])
            if parent:
                h = parent.find(["h2", "h3", "h4"])
                if h:
                    name = _clean_name(h.get_text(strip=True))
        if not name:
            continue

        records.append(
            RestaurantRecord(
                url=full,
                captured_at=captured_at,
                name=name,
                image_url=_card_image(a),
            )
        )
    return records


def parse_page(html: str, url: str, *, blocked: bool = False) -> list[RestaurantRecord]:
    captured_at = datetime.now(timezone.utc).isoformat()
    url = url.split("?")[0]

    if blocked:
        return [
            RestaurantRecord(
                url=url,
                captured_at=captured_at,
                blocked=True,
                skip_reason="Tripadvisor blocked this page",
            )
        ]

    records: list[RestaurantRecord] = []
    seen: set[str] = set()

    current = parse_place_detail(html, url, blocked=False)
    if current.has_data():
        records.append(current)
        seen.add(current.url)

    for item in parse_listing_page(html, url):
        if item.url not in seen:
            records.append(item)
            seen.add(item.url)

    if records:
        return records

    return [
        RestaurantRecord(
            url=url,
            captured_at=captured_at,
            skipped=True,
            skip_reason="No data found — wait for page to load, then click Capture now",
        )
    ]


def parse_restaurant(html: str, url: str, *, blocked: bool = False) -> RestaurantRecord:
    return parse_page(html, url, blocked=blocked)[0]


def parse_restaurant_detail(html: str, url: str, *, blocked: bool = False) -> RestaurantRecord:
    return parse_place_detail(html, url, blocked=blocked)


def parse_html(html: str, url: str) -> RestaurantRecord:
    return parse_restaurant(html, url)
