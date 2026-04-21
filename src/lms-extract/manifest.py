from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Manifest:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, Any] = {"version": 1, "downloads": {}}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as file:
            loaded = json.load(file)
        if isinstance(loaded, dict) and isinstance(loaded.get("downloads"), dict):
            self.data = loaded

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".json.part")
        with tmp_path.open("w", encoding="utf-8") as file:
            json.dump(self.data, file, indent=2, sort_keys=True)
            file.write("\n")
        tmp_path.replace(self.path)

    @staticmethod
    def key(course_id: str, topic: str, final_url: str) -> str:
        raw = f"{course_id}\n{topic}\n{final_url}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def entry(self, key: str) -> dict[str, Any] | None:
        entry = self.data["downloads"].get(key)
        return entry if isinstance(entry, dict) else None

    def recorded_path(self, key: str) -> Path | None:
        entry = self.entry(key)
        if not entry or not entry.get("output_path"):
            return None
        return Path(entry["output_path"])

    def should_skip(self, key: str, expected_size: int | None = None) -> bool:
        entry = self.entry(key)
        if not entry or entry.get("status") != "complete":
            return False

        output_path = Path(entry.get("output_path", ""))
        if not output_path.exists() or not output_path.is_file():
            return False

        recorded_size = entry.get("size")
        check_size = expected_size if expected_size is not None else recorded_size
        return check_size is None or output_path.stat().st_size == check_size

    def record_success(
        self,
        key: str,
        *,
        course_id: str,
        course_name: str | None = None,
        topic: str,
        title: str,
        source_url: str,
        final_url: str,
        output_path: Path,
        size: int | None,
    ) -> None:
        self.data["downloads"][key] = {
            "course_id": course_id,
            "course_name": course_name,
            "topic": topic,
            "title": title,
            "source_url": source_url,
            "final_url": final_url,
            "output_path": str(output_path),
            "size": size if size is not None else output_path.stat().st_size,
            "status": "complete",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.save()
