import pytest

from lms_extrafiliator.cli import (
    _academic_year_tokens,
    _course_key,
    _course_keys,
    _filter_courses_by_academic_year,
    _target_courses,
    _resolve_course,
)
from lms_extrafiliator.errors import LMSExtractError
from lms_extrafiliator.models import Course


class FakeClient:
    def __init__(self, courses: list[Course]) -> None:
        self._courses = courses

    def discover_courses(self) -> list[Course]:
        return self._courses

    def site_url(self, path: str) -> str:
        return f"https://lms.test/{path}"


def test_course_key_uses_trimmed_course_name() -> None:
    course = Course(
        id="4010",
        name="CMSC 126 - Web Programming - Section 1 (Second Semester 2025-2026)",
        url="https://lms.test/course/view.php?id=4010",
    )

    assert _course_key(course) == "CMSC 126"


def test_course_keys_append_lab_for_laboratory_course() -> None:
    courses = [
        Course(id="4049", name="CMSC 126 - Laboratory - Section 1", url="https://lms.test/course/view.php?id=4049"),
    ]

    assert _course_keys(courses) == {"4049": "CMSC 126 Lab"}


def test_resolve_course_accepts_trimmed_course_key() -> None:
    client = FakeClient(
        [
            Course(
                id="4010",
                name="CMSC 126 - Web Programming - Section 1 (Second Semester 2025-2026)",
                url="https://lms.test/course/view.php?id=4010",
            )
        ]
    )

    course = _resolve_course(client, "CMSC 126")

    assert course.id == "4010"
    assert course.name.startswith("CMSC 126 -")


def test_resolve_course_accepts_compact_course_key() -> None:
    client = FakeClient(
        [
            Course(
                id="4010",
                name="CMSC 126 - Web Programming",
                url="https://lms.test/course/view.php?id=4010",
            )
        ]
    )

    assert _resolve_course(client, "cmsc126").id == "4010"


def test_resolve_course_accepts_unique_course_number() -> None:
    client = FakeClient(
        [
            Course(
                id="4010",
                name="CMSC 126 - Web Programming",
                url="https://lms.test/course/view.php?id=4010",
            )
        ]
    )

    assert _resolve_course(client, "126").id == "4010"


def test_resolve_course_keeps_moodle_id_backwards_compatible() -> None:
    client = FakeClient(
        [
            Course(
                id="4010",
                name="CMSC 126 - Web Programming",
                url="https://lms.test/course/view.php?id=4010",
            )
        ]
    )

    assert _resolve_course(client, "4010").name == "CMSC 126 - Web Programming"


def test_resolve_course_prefers_lecture_for_exact_base_key() -> None:
    client = FakeClient(
        [
            Course(id="1", name="CMSC 126 - Lecture - Section 1", url="https://lms.test/course/view.php?id=1"),
            Course(id="2", name="CMSC 126 - Laboratory - Section 1", url="https://lms.test/course/view.php?id=2"),
        ]
    )

    assert _resolve_course(client, "CMSC 126").id == "1"


def test_resolve_course_accepts_lab_detail() -> None:
    client = FakeClient(
        [
            Course(id="1", name="CMSC 126 - Lecture - Section 1", url="https://lms.test/course/view.php?id=1"),
            Course(id="2", name="CMSC 126 - Laboratory - Section 1", url="https://lms.test/course/view.php?id=2"),
        ]
    )

    assert _resolve_course(client, "CMSC 126 Lab").id == "2"


def test_resolve_course_reports_ambiguous_course_key_without_preferred_lecture() -> None:
    client = FakeClient(
        [
            Course(id="1", name="CMSC 126 - Lab A", url="https://lms.test/course/view.php?id=1"),
            Course(id="2", name="CMSC 126 - Lab B", url="https://lms.test/course/view.php?id=2"),
        ]
    )

    with pytest.raises(LMSExtractError, match="ambiguous"):
        _resolve_course(client, "CMSC 126")


def test_course_keys_ignore_non_lab_subject_text_after_hyphen() -> None:
    courses = [
        Course(id="4010", name="CMSC 126 - Web Programming", url="https://lms.test/course/view.php?id=4010"),
    ]

    assert _course_keys(courses) == {"4010": "CMSC 126"}


def test_resolve_course_reports_ambiguous_course_number() -> None:
    client = FakeClient(
        [
            Course(id="1", name="CMSC 126 - Section 1", url="https://lms.test/course/view.php?id=1"),
            Course(id="2", name="BIO 126 - Section 1", url="https://lms.test/course/view.php?id=2"),
        ]
    )

    with pytest.raises(LMSExtractError, match="ambiguous"):
        _resolve_course(client, "126")


def test_course_keys_disambiguate_duplicate_base_keys_with_first_detail() -> None:
    courses = [
        Course(id="4021", name="CMSC 127 - Lecture - Section A", url="https://lms.test/course/view.php?id=4021"),
        Course(id="4049", name="CMSC 127 - Laboratory - Section B", url="https://lms.test/course/view.php?id=4049"),
    ]

    assert _course_keys(courses) == {
        "4021": "CMSC 127",
        "4049": "CMSC 127 Lab",
    }


def test_resolve_course_accepts_disambiguated_duplicate_key() -> None:
    client = FakeClient(
        [
            Course(id="4021", name="CMSC 127 - Lecture - Section A", url="https://lms.test/course/view.php?id=4021"),
            Course(id="4049", name="CMSC 127 - Laboratory - Section B", url="https://lms.test/course/view.php?id=4049"),
        ]
    )

    assert _resolve_course(client, "CMSC 127 Lab").id == "4049"


def test_academic_year_tokens_support_short_and_long_forms() -> None:
    assert _academic_year_tokens("25-26") == {"25-26", "2025-26", "2025-2026"}


def test_filter_courses_by_academic_year_matches_short_year_in_long_course_name() -> None:
    courses = [
        Course(id="1", name="CMSC 126 - Second Semester 2024-2025", url="https://lms.test/course/view.php?id=1"),
        Course(id="2", name="CMSC 127 - Second Semester 2025-2026", url="https://lms.test/course/view.php?id=2"),
        Course(id="3", name="CMSC 128 - AY2025-26", url="https://lms.test/course/view.php?id=3"),
    ]

    filtered = _filter_courses_by_academic_year(courses, "25-26")

    assert [course.id for course in filtered] == ["2", "3"]


def test_target_courses_filters_all_by_academic_year() -> None:
    client = FakeClient(
        [
            Course(id="1", name="CMSC 126 - Second Semester 2024-2025", url="https://lms.test/course/view.php?id=1"),
            Course(id="2", name="CMSC 127 - Second Semester 2025-2026", url="https://lms.test/course/view.php?id=2"),
        ]
    )

    courses = _target_courses(client, all_courses=True, course=None, academic_year="25-26")

    assert [course.id for course in courses] == ["2"]
