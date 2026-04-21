from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Course:
    id: str
    name: str
    url: str


@dataclass(frozen=True)
class Resource:
    course_id: str
    topic: str
    title: str
    url: str
    source_url: str
    course_name: str = ""
    filename_hint: str | None = None


@dataclass(frozen=True)
class Topic:
    course_id: str
    name: str
    section_id: str
    url: str
    resources: list[Resource]
    course_name: str = ""


@dataclass(frozen=True)
class PreparedDownload:
    resource: Resource
    final_url: str
    filename: str
    size: int | None


@dataclass(frozen=True)
class DownloadResult:
    prepared: PreparedDownload
    output_path: str
    status: str
    message: str = ""
