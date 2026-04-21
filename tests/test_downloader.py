from pathlib import Path

from lms_extrafiliator.config import Settings
from lms_extrafiliator.downloader import course_folder_name, download_resources, output_path_for
from lms_extrafiliator.manifest import Manifest
from lms_extrafiliator.models import PreparedDownload, Resource


class DummyClient:
    def __init__(self, prepared: PreparedDownload) -> None:
        self.prepared = prepared

    def prepare_download(self, _resource: Resource) -> PreparedDownload:
        return self.prepared


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        base_url="https://lms.test",
        username="user",
        password="pass",
        download_dir=tmp_path / "downloads",
        auth_mode="http",
        login_path=None,
        state_dir=tmp_path / ".lms-extract",
    )


def make_resource() -> Resource:
    return Resource(
        course_id="42",
        course_name="Biology 101 - Laboratory",
        topic="Week 1",
        title="Lecture Notes",
        url="https://lms.test/mod/resource/view.php?id=100",
        source_url="https://lms.test/course/view.php?id=42",
    )


def make_prepared(resource: Resource, *, filename: str = "lecture.pdf", size: int | None = 10) -> PreparedDownload:
    return PreparedDownload(
        resource=resource,
        final_url="https://lms.test/pluginfile.php/1/file.pdf",
        filename=filename,
        size=size,
    )


def test_output_path_uses_course_name_not_course_id(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    resource = make_resource()
    prepared = make_prepared(resource)
    manifest = Manifest(settings.manifest_path)
    key = manifest.key(resource.course_id, resource.topic, prepared.final_url)

    path = output_path_for(settings, prepared, manifest, key)

    assert path == tmp_path / "downloads" / "Biology 101 Lab" / "Week 1" / "lecture.pdf"


def test_course_folder_name_uses_text_before_first_hyphen() -> None:
    assert course_folder_name("CMSC 101 - Introduction to Computing", "42") == "CMSC 101"


def test_course_folder_name_appends_lab_for_laboratory_course() -> None:
    assert course_folder_name("CMSC 126 - Laboratory - Section 1", "42") == "CMSC 126 Lab"


def test_course_folder_name_falls_back_to_course_id_when_name_is_blank() -> None:
    assert course_folder_name("", "42") == "Course 42"


def test_dry_run_skips_exact_existing_file_without_manifest(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    resource = make_resource()
    prepared = make_prepared(resource, size=3)
    existing = tmp_path / "downloads" / "Biology 101 Lab" / "Week 1" / "lecture.pdf"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"abc")

    results = download_resources(settings, DummyClient(prepared), [resource], dry_run=True)

    assert results[0].status == "skipped"
    assert results[0].output_path == str(existing)


def test_dry_run_skips_matching_file_in_old_numeric_course_folder(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    resource = Resource(
        course_id="42",
        course_name="Biology 101",
        topic="Week 1",
        title="Lecture Notes",
        url="https://lms.test/mod/resource/view.php?id=100",
        source_url="https://lms.test/course/view.php?id=42",
    )
    prepared = make_prepared(resource, filename="lecture.pdf", size=3)
    existing = tmp_path / "downloads" / "42" / "Week 1" / "lecture_notes.pdf"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"abc")

    results = download_resources(settings, DummyClient(prepared), [resource], dry_run=True)

    assert results[0].status == "skipped"
    assert results[0].output_path == str(existing)


def test_download_migrates_manifest_file_from_old_numeric_course_folder(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    resource = make_resource()
    prepared = make_prepared(resource, filename="lecture.pdf", size=3)
    old_path = tmp_path / "downloads" / "42" / "Week 1" / "lecture.pdf"
    old_path.parent.mkdir(parents=True)
    old_path.write_bytes(b"abc")

    manifest = Manifest(settings.manifest_path)
    key = manifest.key(resource.course_id, resource.topic, prepared.final_url)
    manifest.record_success(
        key,
        course_id=resource.course_id,
        course_name=resource.course_name,
        topic=resource.topic,
        title=resource.title,
        source_url=resource.source_url,
        final_url=prepared.final_url,
        output_path=old_path,
        size=3,
    )

    results = download_resources(settings, DummyClient(prepared), [resource], dry_run=False)
    new_path = tmp_path / "downloads" / "Biology 101 Lab" / "Week 1" / "lecture.pdf"

    assert results[0].status == "skipped"
    assert results[0].message == "migrated existing file to course-name folder"
    assert results[0].output_path == str(new_path)
    assert new_path.read_bytes() == b"abc"
    assert not old_path.exists()
    assert Manifest(settings.manifest_path).recorded_path(key) == new_path
