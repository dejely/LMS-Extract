from __future__ import annotations

from urllib.parse import urlparse

import httpx

from .browser_auth import load_browser_cookies
from .config import Settings
from .errors import AuthError, DownloadError, MoodleParseError
from .models import Course, PreparedDownload, Resource, Topic
from .parser import (
    looks_logged_in,
    looks_login_failed,
    parse_courses,
    parse_login_token,
    parse_resource_links,
    parse_topics,
)
from .utils import (
    absolute_url,
    choose_filename,
    is_direct_file_url,
    is_downloadable_or_resource_url,
)


class MoodleClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self.http = httpx.Client(
            base_url=settings.base_url,
            follow_redirects=True,
            timeout=httpx.Timeout(30.0, read=120.0),
            headers={"User-Agent": "lms-extract/0.1.0"},
            transport=transport,
        )

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> "MoodleClient":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def authenticate(self) -> None:
        if self.settings.auth_mode == "browser":
            load_browser_cookies(self.settings, self.http)
            self.verify_browser_session()
            return
        self.login_http()

    def login_http(self) -> None:
        login_url, response = self._load_login_page()
        response.raise_for_status()

        token = parse_login_token(response.text)
        data = {
            "username": self.settings.username or "",
            "password": self.settings.password or "",
        }
        if token:
            data["logintoken"] = token

        login_response = self.http.post(login_url, data=data)
        login_response.raise_for_status()

        if looks_login_failed(login_response.text) and not looks_logged_in(login_response.text):
            raise AuthError("Moodle login failed. Check LMS_USERNAME/LMS_PASSWORD or use browser auth for SSO/MFA.")

    def login_url(self) -> str:
        return self.site_url(self.settings.login_path or "login/index.php")

    def _load_login_page(self) -> tuple[str, httpx.Response]:
        candidates = [self.settings.login_path] if self.settings.login_path else ["login/index.php", "login.php"]
        fallback: tuple[str, httpx.Response] | None = None

        for candidate in candidates:
            if candidate is None:
                continue
            login_url = self.site_url(candidate)
            response = self.http.get(login_url)
            if response.status_code >= 400:
                fallback = (login_url, response)
                continue
            if _contains_login_form(response.text):
                return login_url, response
            fallback = (login_url, response)

        if fallback:
            return fallback
        raise AuthError("Could not find a Moodle login page.")

    def verify_browser_session(self) -> None:
        response = self.http.get(self.site_url("my/"))
        response.raise_for_status()
        if looks_login_failed(response.text) and not looks_logged_in(response.text):
            raise AuthError("Saved browser session is not authenticated. Run 'lms-extract auth browser' again.")

    def discover_courses(self) -> list[Course]:
        pages = ["my/courses.php", "my/", ""]
        courses: dict[str, Course] = {}
        for page in pages:
            response = self.http.get(self.site_url(page))
            if response.status_code >= 400:
                continue
            for course in parse_courses(response.text, self.settings.base_url):
                courses.setdefault(course.id, course)
        return sorted(courses.values(), key=lambda course: int(course.id))

    def get_course_topics(self, course_id: str, course_name: str | None = None) -> list[Topic]:
        course_url = self.site_url(f"course/view.php?id={course_id}")
        response = self.http.get(course_url)
        response.raise_for_status()
        return parse_topics(response.text, self.settings.base_url, course_id, course_url, course_name)

    def site_url(self, path: str) -> str:
        path = path.lstrip("/")
        return f"{self.settings.base_url}/{path}" if path else self.settings.base_url

    def prepare_download(self, resource: Resource) -> PreparedDownload:
        final_url = self.resolve_download_url(resource.url, resource)
        with self.http.stream("GET", final_url, follow_redirects=True) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" in content_type and not is_downloadable_or_resource_url(str(response.url)):
                raise DownloadError(f"Resource did not resolve to a downloadable file: {resource.title}")
            size = _int_header(response.headers.get("content-length"))
            filename = choose_filename(dict(response.headers), str(response.url), resource.filename_hint or resource.title)
            return PreparedDownload(
                resource=resource,
                final_url=str(response.url),
                filename=filename,
                size=size,
            )

    def resolve_download_url(self, url: str, resource: Resource) -> str:
        if "/pluginfile.php" in urlparse(url).path or is_direct_file_url(url):
            return url

        with self.http.stream("GET", url, follow_redirects=True) as response:
            response.raise_for_status()
            final_url = str(response.url)
            content_type = response.headers.get("content-type", "").lower()
            disposition = response.headers.get("content-disposition")

            if disposition or "/pluginfile.php" in urlparse(final_url).path or is_direct_file_url(final_url):
                return final_url
            if "text/html" not in content_type:
                return final_url

            html = _read_text_limited(response)
            links = parse_resource_links(
                html,
                self.settings.base_url,
                resource.course_id,
                resource.course_name,
                resource.topic,
                final_url,
            )
            for candidate in links:
                if candidate.url != url:
                    return candidate.url

        raise MoodleParseError(f"Could not resolve downloadable URL for resource: {resource.title}")


def _read_text_limited(response: httpx.Response, limit: int = 2_000_000) -> str:
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes():
        chunks.append(chunk)
        total += len(chunk)
        if total > limit:
            break
    return b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")


def _contains_login_form(html: str) -> bool:
    lower = html.lower()
    return 'name="username"' in lower and 'name="password"' in lower


def _int_header(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None
