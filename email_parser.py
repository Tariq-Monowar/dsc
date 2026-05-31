"""Extract email addresses from Tripadvisor HTML."""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

ALLOWED_DOMAIN = "tripadvisor.com"
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def is_tripadvisor_url(url: str) -> bool:
    return ALLOWED_DOMAIN in urlparse(url).netloc.lower()


def extract_emails(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []
    seen: set[str] = set()

    def add(raw: str | None) -> None:
        if not raw:
            return
        email = raw.strip().lower()
        if "@" not in email or email in seen:
            return
        if "tripadvisor" in email or "example.com" in email:
            return
        seen.add(email)
        found.append(email)

    for a in soup.find_all("a", href=True):
        href = str(a["href"])
        if href.startswith("mailto:"):
            add(href[7:].split("?")[0])

    for tag in soup.find_all("script", type="application/ld+json"):
        if not tag.string:
            continue
        try:
            data = json.loads(tag.string)
            _emails_from_json(data, add)
        except json.JSONDecodeError:
            continue

    for match in EMAIL_RE.findall(soup.get_text(" ", strip=True)[:100000]):
        add(match)

    for match in EMAIL_RE.findall(html[:300000]):
        add(match)

    return found


def _emails_from_json(obj: object, add: callable) -> None:
    if isinstance(obj, dict):
        if "email" in obj:
            add(str(obj["email"]))
        for v in obj.values():
            _emails_from_json(v, add)
    elif isinstance(obj, list):
        for item in obj:
            _emails_from_json(item, add)
