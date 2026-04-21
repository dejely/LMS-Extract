from pathlib import Path

from lms_extrafiliator.manifest import Manifest


def test_manifest_records_and_skips_completed_download(tmp_path: Path) -> None:
    manifest = Manifest(tmp_path / "manifest.json")
    output = tmp_path / "downloads" / "file.pdf"
    output.parent.mkdir()
    output.write_bytes(b"abc")

    key = manifest.key("42", "Week 1", "https://lms.test/file.pdf")
    manifest.record_success(
        key,
        course_id="42",
        topic="Week 1",
        title="File",
        source_url="https://lms.test/mod/resource/view.php?id=1",
        final_url="https://lms.test/file.pdf",
        output_path=output,
        size=3,
    )

    reloaded = Manifest(tmp_path / "manifest.json")
    assert reloaded.should_skip(key, expected_size=3)
    assert not reloaded.should_skip(key, expected_size=4)

