from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
from rich.console import Console

from .config import Settings
from .errors import AuthError

console = Console()


def capture_browser_session(settings: Settings) -> Path:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise AuthError("Playwright is not installed. Run 'uv sync' and 'uv run playwright install chromium'.") from exc

    settings.state_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(f"{settings.base_url}/{settings.login_path or 'login.php'}")

        console.print("[bold]Complete login in the browser window.[/bold]")
        console.print("After Moodle shows you as logged in, return here and press Enter.")
        input()

        cookies = context.cookies()
        browser.close()

    payload = {
        "base_url": settings.base_url,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "cookies": cookies,
    }
    with settings.browser_session_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, sort_keys=True)
        file.write("\n")
    return settings.browser_session_path


def load_browser_cookies(settings: Settings, client: httpx.Client) -> None:
    if not settings.browser_session_path.exists():
        raise AuthError("Browser session not found. Run 'lms-extract auth browser' first.")

    with settings.browser_session_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    if payload.get("base_url") != settings.base_url:
        raise AuthError("Browser session was captured for a different LMS_BASE_URL.")

    cookies = payload.get("cookies", [])
    if not isinstance(cookies, list) or not cookies:
        raise AuthError("Browser session file does not contain cookies.")

    for cookie in cookies:
        if not isinstance(cookie, dict) or "name" not in cookie or "value" not in cookie:
            continue
        client.cookies.set(
            str(cookie["name"]),
            str(cookie["value"]),
            domain=cookie.get("domain"),
            path=cookie.get("path", "/"),
        )
