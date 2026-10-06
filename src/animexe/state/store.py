from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, TypeVar

from ..models import AnimeRecord, EpisodeRecord, SchedulerState, utc_now

T = TypeVar("T")


class StateStore:
    """Small Git-friendly JSON state store with atomic file replacement."""

    FILENAMES = {
        "anime": "anime.json",
        "episodes": "episodes.json",
        "scheduler": "scheduler.json",
        "generation_history": "generation_history.json",
        "provider_cache": "provider_cache.json",
    }

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    def ensure(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        defaults: dict[str, Any] = {
            "anime": {"schema_version": 1, "items": []},
            "episodes": {"schema_version": 1, "items": []},
            "scheduler": {
                "schema_version": 1,
                **asdict(SchedulerState()),
            },
            "generation_history": {"schema_version": 1, "items": []},
            "provider_cache": {"schema_version": 1, "items": []},
        }
        for name, default in defaults.items():
            path = self.path_for(name)
            if not path.exists():
                self._atomic_write(path, default)

    def path_for(self, name: str) -> Path:
        try:
            filename = self.FILENAMES[name]
        except KeyError as exc:
            raise KeyError(f"unknown state file: {name}") from exc
        return self.data_dir / filename

    def _read_json(self, name: str) -> dict[str, Any]:
        self.ensure()
        path = self.path_for(name)
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{path} must contain a JSON object")
        return data

    def _atomic_write(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_name = handle.name
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)

    def list_anime(self) -> list[AnimeRecord]:
        records = []
        for item in self._read_json("anime").get("items", []):
            record = AnimeRecord(**item)
            record.validate()
            records.append(record)
        return records

    def save_anime(self, record: AnimeRecord) -> None:
        record.validate()
        payload = self._read_json("anime")
        items = [item for item in payload.get("items", []) if item.get("id") != record.id]
        record.updated_at = utc_now()
        items.append(asdict(record))
        items.sort(key=lambda item: (item.get("title", "").lower(), item.get("season", 1)))
        payload["items"] = items
        self._atomic_write(self.path_for("anime"), payload)

    def list_episodes(self, anime_id: str | None = None) -> list[EpisodeRecord]:
        records = []
        for item in self._read_json("episodes").get("items", []):
            if anime_id is not None and item.get("anime_id") != anime_id:
                continue
            item = dict(item)
            item.setdefault("analysis_manifest", None)
            item.setdefault("scene_manifest", None)
            item.setdefault("transcript_manifest", None)
            item.setdefault("story_manifest", None)
            record = EpisodeRecord(**item)
            record.validate()
            records.append(record)
        return records

    def save_episode(self, record: EpisodeRecord) -> None:
        record.validate()
        payload = self._read_json("episodes")
        items = [
            item for item in payload.get("items", [])
            if item.get("id") != record.id
        ]
        record.updated_at = utc_now()
        items.append(asdict(record))
        items.sort(key=lambda item: (item.get("anime_id", ""), item.get("episode_number", 0)))
        payload["items"] = items
        self._atomic_write(self.path_for("episodes"), payload)

    def load_scheduler(self) -> SchedulerState:
        data = self._read_json("scheduler")
        raw = {k: v for k, v in data.items() if k != "schema_version"}
        state = SchedulerState(**raw)
        state.validate()
        return state

    def save_scheduler(self, state: SchedulerState) -> None:
        state.validate()
        payload = {"schema_version": 1, **asdict(state)}
        self._atomic_write(self.path_for("scheduler"), payload)
