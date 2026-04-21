from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from rich.console import Console
from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn, TimeRemainingColumn, TransferSpeedColumn

from .config import Settings
from .course_names import display_course_key
from .errors import DownloadError
from .manifest import Manifest
from .models import DownloadResult, PreparedDownload, Resource
from .moodle import MoodleClient
from .utils import sanitize_path_part, unique_path

console = Console()


@dataclass(frozen=True)
class ExistingDownload:
    path: Path
    reason: str


def output_path_for(settings: Settings, prepared: PreparedDownload, manifest: Manifest, key: str) -> Path:
    base_path = base_output_path_for(settings, prepared)
    recorded = manifest.recorded_path(key)
    if recorded and recorded == base_path:
        return recorded

    return unique_path(base_path)


def base_output_path_for(settings: Settings, prepared: PreparedDownload) -> Path:
    course_dir = course_folder_name(prepared.resource.course_name, prepared.resource.course_id)
    topic_dir = sanitize_path_part(prepared.resource.topic, "topic")
    filename = sanitize_path_part(prepared.filename, "download")
    return settings.download_dir / course_dir / topic_dir / filename


def course_folder_name(course_name: str, course_id: str) -> str:
    return display_course_key(course_name, course_id)


def find_existing_download(
    settings: Settings,
    prepared: PreparedDownload,
    manifest: Manifest,
    key: str,
) -> ExistingDownload | None:
    if manifest.should_skip(key, prepared.size):
        recorded = manifest.recorded_path(key)
        if recorded:
            return ExistingDownload(recorded, "already in manifest")

    base_path = base_output_path_for(settings, prepared)
    if _file_matches(base_path, prepared.size, allow_unknown_size=True):
        return ExistingDownload(base_path, "matching file already exists")

    topic_matches = _find_existing_in_topic_dirs(settings.download_dir, base_path, prepared)
    if topic_matches:
        return topic_matches

    exact_match = _find_exact_name_in_downloads(settings.download_dir, base_path.name, prepared.size)
    if exact_match:
        return exact_match

    return None


def download_resources(
    settings: Settings,
    client: MoodleClient,
    resources: list[Resource],
    *,
    dry_run: bool = False,
) -> list[DownloadResult]:
    manifest = Manifest(settings.manifest_path)
    results: list[DownloadResult] = []

    for resource in resources:
        try:
            prepared = client.prepare_download(resource)
            key = manifest.key(resource.course_id, resource.topic, prepared.final_url)
            existing = find_existing_download(settings, prepared, manifest, key)
            output_path = output_path_for(settings, prepared, manifest, key)

            if dry_run:
                if existing:
                    results.append(DownloadResult(prepared, str(existing.path), "skipped", existing.reason))
                else:
                    results.append(DownloadResult(prepared, str(output_path), "planned"))
                continue

            if existing:
                existing = migrate_existing_download(settings, prepared, existing)
                manifest.record_success(
                    key,
                    course_id=resource.course_id,
                    course_name=resource.course_name,
                    topic=resource.topic,
                    title=resource.title,
                    source_url=resource.source_url,
                    final_url=prepared.final_url,
                    output_path=existing.path,
                    size=prepared.size,
                )
                results.append(DownloadResult(prepared, str(existing.path), "skipped", existing.reason))
                continue

            _download_one(client, prepared, output_path)
            manifest.record_success(
                key,
                course_id=resource.course_id,
                course_name=resource.course_name,
                topic=resource.topic,
                title=resource.title,
                source_url=resource.source_url,
                final_url=prepared.final_url,
                output_path=output_path,
                size=prepared.size,
            )
            results.append(DownloadResult(prepared, str(output_path), "downloaded"))
        except Exception as exc:
            results.append(
                DownloadResult(
                    PreparedDownload(resource=resource, final_url=resource.url, filename=resource.title, size=None),
                    "",
                    "failed",
                    str(exc),
                )
            )

    return results


def _download_one(client: MoodleClient, prepared: PreparedDownload, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = output_path.with_name(f"{output_path.name}.part")
    if part_path.exists():
        part_path.unlink()

    with client.http.stream("GET", prepared.final_url, follow_redirects=True) as response:
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" in content_type and not prepared.filename.lower().endswith((".html", ".htm")):
            raise DownloadError(f"Expected a file but received HTML for {prepared.resource.title}")

        total = _content_length(response.headers.get("content-length")) or prepared.size
        progress = Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
            transient=True,
        )
        with progress:
            task = progress.add_task(prepared.filename, total=total)
            with part_path.open("wb") as file:
                for chunk in response.iter_bytes():
                    if not chunk:
                        continue
                    file.write(chunk)
                    progress.update(task, advance=len(chunk))

    part_path.replace(output_path)


def _content_length(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _find_existing_in_topic_dirs(
    download_dir: Path,
    base_path: Path,
    prepared: PreparedDownload,
) -> ExistingDownload | None:
    if not download_dir.exists():
        return None

    topic_dir_name = base_path.parent.name.casefold()
    expected_name = base_path.name
    topic_dirs = [
        path
        for path in download_dir.rglob("*")
        if path.is_dir() and path.name.casefold() == topic_dir_name
    ]

    for topic_dir in topic_dirs:
        exact = topic_dir / expected_name
        if _file_matches(exact, prepared.size, allow_unknown_size=True):
            return ExistingDownload(exact, "matching file already exists in a topic folder")

    for topic_dir in topic_dirs:
        fuzzy = _find_fuzzy_name_match(topic_dir, expected_name, prepared.size)
        if fuzzy:
            return ExistingDownload(fuzzy, "similar downloaded file already exists in a topic folder")

    return None


def migrate_existing_download(
    settings: Settings,
    prepared: PreparedDownload,
    existing: ExistingDownload,
) -> ExistingDownload:
    if not _should_migrate_existing(settings, prepared, existing.path):
        return existing

    target = base_output_path_for(settings, prepared).parent / existing.path.name
    if existing.path == target:
        return existing
    if target.exists():
        if _file_matches(target, prepared.size, allow_unknown_size=True):
            return ExistingDownload(target, "matching file already exists")
        return existing

    target.parent.mkdir(parents=True, exist_ok=True)
    old_parent = existing.path.parent
    existing.path.replace(target)
    _remove_empty_parents(old_parent, settings.download_dir)
    return ExistingDownload(target, "migrated existing file to course-name folder")


def _find_exact_name_in_downloads(download_dir: Path, expected_name: str, expected_size: int | None) -> ExistingDownload | None:
    if not download_dir.exists() or expected_size is None:
        return None

    for path in download_dir.rglob("*"):
        if not path.is_file() or path.name.endswith(".part"):
            continue
        if path.name.casefold() == expected_name.casefold() and _file_matches(path, expected_size):
            return ExistingDownload(path, "matching file already exists in downloads")
    return None


def _find_fuzzy_name_match(topic_dir: Path, expected_name: str, expected_size: int | None) -> Path | None:
    if expected_size is None:
        return None

    for path in topic_dir.iterdir():
        if not path.is_file() or path.name.endswith(".part"):
            continue
        if _names_overlap(path.name, expected_name) and _file_matches(path, expected_size):
            return path
    return None


def _file_matches(path: Path, expected_size: int | None, *, allow_unknown_size: bool = False) -> bool:
    if not path.exists() or not path.is_file():
        return False
    if expected_size is None:
        return allow_unknown_size
    return path.stat().st_size == expected_size


def _names_overlap(existing_name: str, expected_name: str) -> bool:
    existing = Path(existing_name)
    expected = Path(expected_name)
    if existing.suffix.casefold() != expected.suffix.casefold():
        return False

    existing_stem = _normalize_name(existing.stem)
    expected_stem = _normalize_name(expected.stem)
    if len(existing_stem) < 4 or len(expected_stem) < 4:
        return False
    return existing_stem in expected_stem or expected_stem in existing_stem


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _should_migrate_existing(settings: Settings, prepared: PreparedDownload, path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    try:
        relative = path.relative_to(settings.download_dir)
    except ValueError:
        return False
    if not relative.parts:
        return False

    old_course_dir = sanitize_path_part(prepared.resource.course_id, "course")
    current_course_dir = course_folder_name(prepared.resource.course_name, prepared.resource.course_id)
    return relative.parts[0] == old_course_dir and old_course_dir != current_course_dir


def _remove_empty_parents(start: Path, stop: Path) -> None:
    current = start
    while current != stop and current != current.parent:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent
