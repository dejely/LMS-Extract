from lms_extrafiliator.utils import (
    choose_filename,
    is_downloadable_or_resource_url,
    normalize_base_url,
    sanitize_path_part,
)


def test_normalize_base_url_adds_https_and_strips_trailing_slash() -> None:
    assert normalize_base_url("example.edu/") == "https://example.edu"


def test_sanitize_path_part_removes_invalid_chars() -> None:
    assert sanitize_path_part(' Week 1: Intro / "Files" ') == "Week 1_ Intro _ _Files_"


def test_detects_resource_and_direct_file_urls() -> None:
    assert is_downloadable_or_resource_url("https://lms.test/mod/resource/view.php?id=10")
    assert is_downloadable_or_resource_url("https://lms.test/pluginfile.php/1/mod_resource/content/file.pdf")
    assert is_downloadable_or_resource_url("https://lms.test/files/slides.pptx")


def test_choose_filename_prefers_content_disposition() -> None:
    headers = {"content-disposition": 'attachment; filename="lecture.pdf"'}
    assert choose_filename(headers, "https://lms.test/download?id=1", "fallback") == "lecture.pdf"

