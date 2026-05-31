"""Visible Chrome + capture fields from the tab you are actually viewing."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from browser_factory import BrowserConfig, create_driver, is_blocked_page
from parser import RestaurantRecord, is_tripadvisor_url, parse_page, validate_tripadvisor_url

OnCapture = Callable[[RestaurantRecord, int], None]
OnStatus = Callable[[str], None]
OnWarning = Callable[[str], None]


@dataclass
class BrowseSession:
    restaurants: list[RestaurantRecord] = field(default_factory=list)
    _seen_urls: set[str] = field(default_factory=set)

    def add(self, record: RestaurantRecord, *, force: bool = False) -> int | None:
        if record.skipped or record.blocked or not record.has_data():
            return None
        if record.url in self._seen_urls and not force:
            return None
        self._seen_urls.add(record.url)
        self.restaurants.append(record)
        return len(self.restaurants)

    def to_dict(self) -> dict[str, Any]:
        return {
            "restaurant_count": len(self.restaurants),
            "restaurants": [r.to_dict() for r in self.restaurants],
        }


def _focus_tripadvisor_tab(driver: Any) -> str:
    """Use the Tripadvisor tab the user is browsing (not the first/blank tab)."""
    chosen = driver.current_window_handle
    for handle in driver.window_handles:
        driver.switch_to.window(handle)
        try:
            if is_tripadvisor_url(driver.current_url):
                chosen = handle
        except Exception:
            continue
    driver.switch_to.window(chosen)
    return driver.current_url


class BrowserTracker:
    def __init__(
        self,
        on_capture: OnCapture,
        on_status: OnStatus,
        on_warning: OnWarning,
        config: BrowserConfig | None = None,
    ) -> None:
        self._on_capture = on_capture
        self._on_status = on_status
        self._on_warning = on_warning
        self.config = config or BrowserConfig()
        self.session = BrowseSession()
        self._driver: Any = None
        self._watch_thread: threading.Thread | None = None
        self._running = False
        self._last_url = ""
        self._poll_seconds = 2.0

    @property
    def is_running(self) -> bool:
        return self._running and self._driver is not None

    def start(self, start_url: str = "https://www.tripadvisor.com/") -> None:
        if self.is_running:
            return
        validate_tripadvisor_url(start_url)
        self._driver = create_driver(self.config)
        self._running = True
        self._last_url = ""
        if not self.config.use_manual_chrome:
            self._driver.get(start_url)
        time.sleep(1)
        _focus_tripadvisor_tab(self._driver)
        time.sleep(1)
        if is_blocked_page(self._driver.page_source, self._driver.title):
            self._on_warning(
                "BLOCKED by Tripadvisor — use Manual Chrome + proxy, or wait 1 hour."
            )
        else:
            self._on_status(
                "Connected — browse any page, then click Capture now (uses active tab)."
            )
        self._capture_page(force=True)
        self._watch_thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._watch_thread.start()

    def capture_now(self) -> None:
        if not self._driver:
            return
        _focus_tripadvisor_tab(self._driver)
        if not is_tripadvisor_url(self._driver.current_url):
            self._on_warning("Only tripadvisor.com is allowed.")
            return
        self._capture_page(force=True)

    def stop(self) -> None:
        self._running = False
        if self._driver:
            if not self.config.use_manual_chrome:
                try:
                    self._driver.quit()
                except Exception:
                    pass
            self._driver = None
        self._on_status(
            "Tracker disconnected." if self.config.use_manual_chrome else "Browser closed."
        )

    def _watch_loop(self) -> None:
        while self._running and self._driver:
            try:
                _focus_tripadvisor_tab(self._driver)
                url = self._driver.current_url
            except Exception:
                break

            if not is_tripadvisor_url(url):
                if url and url != "about:blank":
                    self._on_warning(f"Left Tripadvisor: {url[:80]}…")
                time.sleep(self._poll_seconds)
                continue

            if url != self._last_url:
                self._capture_page(force=False)
                self._last_url = url

            time.sleep(self._poll_seconds)

    def _capture_page(self, force: bool = False) -> None:
        assert self._driver is not None
        _focus_tripadvisor_tab(self._driver)
        time.sleep(0.5)
        url = self._driver.current_url.split("?")[0]
        html = self._driver.page_source
        title = self._driver.title
        blocked = is_blocked_page(html, title)
        records = parse_page(html, url, blocked=blocked)

        if blocked:
            self._on_warning(
                "BLOCKED — use Manual Chrome + residential proxy, or wait 30–60 min"
            )
            return

        if len(records) == 1 and records[0].skipped:
            self._on_status(records[0].skip_reason or "Nothing found — click Capture now")
            return

        added = 0
        for record in records:
            count = self.session.add(record, force=force)
            if count is not None:
                added += 1
                self._on_capture(record, count)

        if added:
            self._on_status(
                f"Saved {added} item(s) — total {len(self.session.restaurants)}"
            )
        elif records and records[0].has_data():
            self._on_status("Already saved — click Capture now to refresh this page")
