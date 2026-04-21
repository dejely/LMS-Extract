from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup, Tag

from .models import Course, Resource, Topic
from .utils import (
    absolute_url,
    collapse_whitespace,
    is_downloadable_or_resource_url,
)

COURSE_ID_RE = re.compile(r"/course/view\.php(?:\?[^#]*)?$")


def parse_login_token(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    token_input = soup.find("input", attrs={"name": "logintoken"})
    if not isinstance(token_input, Tag):
        return None
    value = token_input.get("value")
    return str(value) if value else None


def looks_logged_in(html: str) -> bool:
    lower = html.lower()
    return "logout.php" in lower or "data-title=\"logout\"" in lower or "login/logout.php" in lower


def looks_login_failed(html: str) -> bool:
    lower = html.lower()
    return (
        "loginerrormessage" in lower
        or "invalid login" in lower
        or "invalid username" in lower
        or "name=\"username\"" in lower and "name=\"password\"" in lower
    )


def parse_courses(html: str, base_url: str) -> list[Course]:
    soup = BeautifulSoup(html, "html.parser")
    courses: dict[str, Course] = {}

    for link in soup.find_all("a", href=True):
        href = str(link["href"])
        url = absolute_url(base_url, href)
        parsed = urlparse(url)
        if not COURSE_ID_RE.search(parsed.path):
            continue

        course_id = parse_qs(parsed.query).get("id", [None])[0]
        if not course_id or not course_id.isdigit():
            continue

        name = _course_name_from_link(link, course_id)
        courses.setdefault(course_id, Course(id=course_id, name=name, url=url))

    return sorted(courses.values(), key=lambda course: int(course.id))


def parse_course_title(html: str, course_id: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for selector in (".page-header-headings h1", "header h1", "h1"):
        element = soup.select_one(selector)
        if element:
            text = _visible_text(element)
            if text:
                return text

    title = soup.find("title")
    if isinstance(title, Tag):
        text = _visible_text(title)
        if text:
            return collapse_whitespace(text.split("|", 1)[0])

    return f"Course {course_id}"


def parse_topics(
    html: str,
    base_url: str,
    course_id: str,
    course_url: str,
    course_name: str | None = None,
) -> list[Topic]:
    soup = BeautifulSoup(html, "html.parser")
    resolved_course_name = course_name or parse_course_title(html, course_id)
    sections = _find_sections(soup)
    if not sections:
        resources = _parse_resources(soup, base_url, course_id, resolved_course_name, "General", course_url)
        return [
            Topic(
                course_id=course_id,
                course_name=resolved_course_name,
                name="General",
                section_id="0",
                url=course_url,
                resources=resources,
            )
        ]

    topics: list[Topic] = []
    for index, section in enumerate(sections, start=1):
        section_id = _section_id(section, index)
        name = _section_name(section, index)
        resources = _parse_resources(section, base_url, course_id, resolved_course_name, name, course_url)
        topics.append(
            Topic(
                course_id=course_id,
                course_name=resolved_course_name,
                name=name,
                section_id=section_id,
                url=course_url,
                resources=resources,
            )
        )

    return topics


def parse_resource_links(
    html: str,
    base_url: str,
    course_id: str,
    course_name: str,
    topic: str,
    source_url: str,
) -> list[Resource]:
    soup = BeautifulSoup(html, "html.parser")
    return _parse_resources(soup, base_url, course_id, course_name, topic, source_url)


def _course_name_from_link(link: Tag, course_id: str) -> str:
    title = link.get("title") or link.get("aria-label")
    if title:
        return collapse_whitespace(str(title))

    text = _visible_text(link)
    if text:
        return text

    for parent in link.parents:
        if not isinstance(parent, Tag):
            continue
        parent_text = _visible_text(parent)
        if parent_text:
            return parent_text[:180]

    return f"Course {course_id}"


def _find_sections(soup: BeautifulSoup) -> list[Tag]:
    selectors = [
        "li.section",
        "section.section",
        "div.course-section",
        "li[data-sectionid]",
        "div[data-sectionid]",
    ]
    sections: list[Tag] = []
    seen: set[int] = set()
    for selector in selectors:
        for section in soup.select(selector):
            if id(section) not in seen:
                sections.append(section)
                seen.add(id(section))
    return sections


def _section_id(section: Tag, index: int) -> str:
    for attr in ("data-sectionid", "data-id", "data-number"):
        value = section.get(attr)
        if value is not None:
            return str(value)
    section_id = section.get("id")
    if section_id:
        return str(section_id)
    return str(index)


def _section_name(section: Tag, index: int) -> str:
    candidates = [
        ".sectionname",
        ".section-title",
        "[data-for='section_title']",
        "h2",
        "h3",
        "h4",
    ]
    for selector in candidates:
        element = section.select_one(selector)
        if element:
            text = _visible_text(element)
            if text:
                return text

    label = section.get("aria-label")
    if label:
        return collapse_whitespace(str(label))

    return f"Section {index}"


def _parse_resources(
    root: Tag | BeautifulSoup,
    base_url: str,
    course_id: str,
    course_name: str,
    topic: str,
    source_url: str,
) -> list[Resource]:
    resources: list[Resource] = []
    seen: set[str] = set()

    for link in root.find_all("a", href=True):
        href = str(link["href"])
        url = absolute_url(base_url, href)
        if not is_downloadable_or_resource_url(url) or url in seen:
            continue
        seen.add(url)

        title = _resource_title(link)
        resources.append(
            Resource(
                course_id=course_id,
                course_name=course_name,
                topic=topic,
                title=title,
                url=url,
                source_url=source_url,
                filename_hint=title,
            )
        )

    return resources


def _resource_title(link: Tag) -> str:
    instance_name = link.select_one(".instancename")
    if instance_name:
        text = _visible_text(instance_name)
        if text:
            return text

    title = link.get("title") or link.get("aria-label")
    if title:
        return collapse_whitespace(str(title))

    text = _visible_text(link)
    return text or "download"


def _visible_text(element: Tag) -> str:
    clone = BeautifulSoup(str(element), "html.parser")
    for hidden in clone.select(".accesshide, .sr-only, .visually-hidden, [aria-hidden='true']"):
        hidden.decompose()
    return collapse_whitespace(clone.get_text(" ", strip=True))
