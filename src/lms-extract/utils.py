from __future__ import annotations

import re
from email.message import Message
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse


DOWNLOADABLE_EXTENSIONS = {
    ".7z",
    ".csv",
    ".doc",
    ".docx",
    ".gif",
    ".jpeg",
    ".jpg",
    ".mp3",
    ".mp4",
    ".odp",
    ".ods",
    ".odt",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".rar",
    ".txt",
    ".xls",
    ".xlsx",
    ".zip",
}

RESOURCE_PATH_MARKERS = (
    "/mod/resource/view.php",
    "/mod/folder/view.php",
    "/pluginfile.php",
)

INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WHITESPACE = re.compile(r"\s+")


def normalize_base_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.scheme:
        url = f"https://{url.strip()}"
        parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Invalid LMS_BASE_URL: {url}")
    return url.rstrip("/")


def absolute_url(base_url: str, href: str) -> str:
    return urljoin(f"{base_url.rstrip('/')}/", href)


def collapse_whitespace(value: str) -> str:
    return WHITESPACE.sub(" ", value).strip()


def sanitize_path_part(value: str, fallback: str = "untitled") -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("_", collapse_whitespace(value))
    cleaned = cleaned.strip(" .")
    return cleaned[:180] or fallback


def is_direct_file_url(url: str) -> bool:
    path = unquote(urlparse(url).path).lower()
    return Path(path).suffix in DOWNLOADABLE_EXTENSIONS


def is_downloadable_or_resource_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(marker in path for marker in RESOURCE_PATH_MARKERS) or is_direct_file_url(url)


def filename_from_url(url: str) -> str | None:
    name = Path(unquote(urlparse(url).path)).name
    return sanitize_path_part(name) if name else None


def filename_from_content_disposition(value: str | None) -> str | None:
    if not value:
        return None

    message = Message()
    message["content-disposition"] = value
    params = message.get_params(header="content-disposition", failobj=[])
    for key, param_value in params:
        if key.lower() == "filename*" and "''" in param_value:
            return sanitize_path_part(unquote(param_value.split("''", 1)[1]))
        if key.lower() == "filename":
            return sanitize_path_part(param_value)
    return None


def choose_filename(headers: dict[str, str], url: str, fallback: str) -> str:
    disposition = headers.get("content-disposition") or headers.get("Content-Disposition")
    return (
        filename_from_content_disposition(disposition)
        or filename_from_url(url)
        or sanitize_path_part(fallback, "download")
    )


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 1
    while True:
        candidate = parent / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
        index += 1

