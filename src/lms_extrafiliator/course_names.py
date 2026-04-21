from __future__ import annotations

from .utils import collapse_whitespace, sanitize_path_part


def base_course_key(course_name: str, course_id: str) -> str:
    base_name = course_name.split("-", 1)[0].strip() if course_name else ""
    return sanitize_path_part(base_name, f"Course {course_id}")


def display_course_key(course_name: str, course_id: str) -> str:
    base_key = base_course_key(course_name, course_id)
    detail = select_course_key_detail(course_name)
    return f"{base_key} {detail}" if detail else base_key


def select_course_key_detail(course_name: str) -> str:
    parts = [collapse_whitespace(part) for part in course_name.split("-")]
    for part in parts[1:]:
        normalized = part.casefold()
        if not part or is_lecture_detail(normalized):
            continue
        if "lab" in normalized or "laboratory" in normalized:
            return "Lab"
    return ""


def is_lecture_course(course_name: str) -> bool:
    parts = [collapse_whitespace(part) for part in course_name.split("-")]
    details = [part.casefold() for part in parts[1:] if part]
    return bool(details) and all(is_lecture_detail(detail) for detail in details)


def is_lecture_detail(value: str) -> bool:
    return (
        "lecture" in value
        or "lec" in value
        or "section" in value
        or "second semester" in value
        or "first semester" in value
        or "midyear" in value
        or "ay" in value
    )

