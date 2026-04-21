from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

from .errors import ConfigError
from .utils import normalize_base_url


@dataclass(frozen=True)
class Settings:
    base_url: str
    username: str | None
    password: str | None
    download_dir: Path
    auth_mode: str
    login_path: str | None
    state_dir: Path

    @property
    def manifest_path(self) -> Path:
        return self.state_dir / "manifest.json"

    @property
    def browser_session_path(self) -> Path:
        return self.state_dir / "browser-session.json"


def load_config(env_path: str | Path = ".env", require_credentials: bool | None = None) -> Settings:
    env_file = Path(env_path)
    values = dict(dotenv_values(env_file)) if env_file.exists() else {}

    def read(name: str, default: str | None = None) -> str | None:
        return os.environ.get(name) or values.get(name) or default

    base_url = read("LMS_BASE_URL")
    username = read("LMS_USERNAME")
    password = read("LMS_PASSWORD")
    download_dir = Path(read("DOWNLOAD_DIR", "downloads") or "downloads")
    auth_mode = (read("LMS_AUTH_MODE", "http") or "http").strip().lower()
    login_path = _clean_optional_path(read("LMS_LOGIN_PATH"))
    state_dir = Path(read("LMS_STATE_DIR", ".lms-extract") or ".lms-extract")

    if auth_mode not in {"http", "browser"}:
        raise ConfigError("LMS_AUTH_MODE must be either 'http' or 'browser'.")
    if not base_url:
        raise ConfigError("LMS_BASE_URL is required in .env or the environment.")

    if require_credentials is None:
        require_credentials = auth_mode == "http"
    if require_credentials and (not username or not password):
        raise ConfigError("LMS_USERNAME and LMS_PASSWORD are required for HTTP login.")

    try:
        normalized_base_url = normalize_base_url(base_url)
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc

    return Settings(
        base_url=normalized_base_url,
        username=username,
        password=password,
        download_dir=download_dir,
        auth_mode=auth_mode,
        login_path=login_path,
        state_dir=state_dir,
    )


def _clean_optional_path(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned or cleaned.lower() == "auto":
        return None
    return cleaned.lstrip("/")
