"""Launch or attach to Chrome; optional proxy; match installed Chrome version."""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

BLOCK_MARKERS = (
    "access is temporarily restricted",
    "automated (bot) activity",
    "unusual activity from your device",
)

DEFAULT_DEBUG_PORT = 9222
SCRAPER_PROFILE_DIR = Path(os.environ.get("LOCALAPPDATA", ".")) / "tripadvisor-scraper-chrome"


@dataclass
class BrowserConfig:
    proxy: str = ""
    use_stealth: bool = True
    chrome_version: int | None = None
    use_manual_chrome: bool = True  # attach to normal Chrome — best vs blocks
    debug_port: int = DEFAULT_DEBUG_PORT

    def normalized_proxy(self) -> str | None:
        raw = self.proxy.strip()
        if not raw:
            return None
        if "://" not in raw:
            raw = "http://" + raw
        parsed = urlparse(raw)
        if not parsed.hostname:
            raise ValueError(
                "Invalid proxy. Examples: host:port  or  http://user:pass@host:port"
            )
        return raw


def detect_chrome_major_version() -> int | None:
    if sys.platform == "win32":
        import winreg

        for hive, path in (
            (winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Google\Chrome\BLBeacon"),
        ):
            try:
                key = winreg.OpenKey(hive, path)
                version, _ = winreg.QueryValueEx(key, "version")
                return int(str(version).split(".")[0])
            except OSError:
                continue

        for exe in (
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(
                r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
            ),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ):
            if os.path.isfile(exe):
                try:
                    out = subprocess.check_output(
                        [exe, "--version"],
                        text=True,
                        timeout=10,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    m = re.search(r"(\d+)\.", out)
                    if m:
                        return int(m.group(1))
                except Exception:
                    continue

    for cmd in ("google-chrome", "google-chrome-stable", "chromium"):
        try:
            out = subprocess.check_output(
                [cmd, "--version"], text=True, stderr=subprocess.DEVNULL, timeout=10
            )
            m = re.search(r"(\d+)\.", out)
            if m:
                return int(m.group(1))
        except Exception:
            continue
    return None


def find_chrome_exe() -> str:
    candidates = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    raise FileNotFoundError("Google Chrome not found. Install Chrome first.")


def is_debug_port_open(port: int = DEFAULT_DEBUG_PORT) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def wait_for_debug_port(port: int = DEFAULT_DEBUG_PORT, timeout: float = 25.0) -> bool:
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_debug_port_open(port):
            return True
        time.sleep(0.4)
    return False


def is_blocked_page(html: str, title: str | None = None) -> bool:
    blob = (html[:12000] + " " + (title or "")).lower()
    return any(m in blob for m in BLOCK_MARKERS)


def launch_manual_chrome(
    start_url: str = "https://www.tripadvisor.com/",
    port: int = DEFAULT_DEBUG_PORT,
    proxy: str | None = None,
) -> None:
    """Start real Chrome (no automation banner). Tracker connects on debug port."""
    SCRAPER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    exe = find_chrome_exe()
    args = [
        exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={SCRAPER_PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        start_url,
    ]
    if proxy:
        args.insert(-1, f"--proxy-server={proxy}")
    subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0,
    )


def _apply_proxy(options: Any, proxy: str) -> None:
    options.add_argument(f"--proxy-server={proxy}")


def _apply_stealth_selenium(options: Any) -> None:
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--disable-blink-features=AutomationControlled")


def _attach_driver(port: int, version_main: int | None) -> Any:
    import undetected_chromedriver as uc

    options = uc.ChromeOptions()
    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
    kwargs: dict[str, Any] = {"options": options}
    if version_main is not None:
        kwargs["version_main"] = version_main
    return uc.Chrome(**kwargs)


def create_driver(config: BrowserConfig) -> Any:
    version_main = config.chrome_version or detect_chrome_major_version()

    if config.use_manual_chrome:
        port = config.debug_port
        if not is_debug_port_open(port):
            raise ConnectionError(
                f"Chrome is not running on port {port}.\n\n"
                "Click «Start manual Chrome» first, wait for Tripadvisor to load, "
                "then click «Connect tracker»."
            )
        return _attach_driver(port, version_main)

    proxy = config.normalized_proxy() if config.proxy.strip() else None

    if config.use_stealth:
        try:
            import undetected_chromedriver as uc

            options = uc.ChromeOptions()
            options.add_argument("--start-maximized")
            options.add_argument("--lang=en-US")
            if proxy:
                _apply_proxy(options, proxy)

            kwargs: dict[str, Any] = {"options": options, "use_subprocess": True}
            if version_main is not None:
                kwargs["version_main"] = version_main

            try:
                return uc.Chrome(**kwargs)
            except Exception:
                if version_main and version_main > 1:
                    kwargs["version_main"] = version_main - 1
                    return uc.Chrome(**kwargs)
                raise
        except ImportError:
            pass

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--lang=en-US")
    _apply_stealth_selenium(options)
    if proxy:
        _apply_proxy(options, proxy)
    return webdriver.Chrome(options=options)
