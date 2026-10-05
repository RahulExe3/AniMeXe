from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectPaths:
    """Canonical filesystem layout for one AniMeXe checkout."""

    root: Path

    @property
    def config(self) -> Path:
        return self.root / "config"

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def workspace(self) -> Path:
        return self.root / "workspace"

    @property
    def assets(self) -> Path:
        return self.root / "assets"

    def ensure(self) -> None:
        for path in (
            self.config,
            self.data,
            self.workspace,
            self.assets,
        ):
            path.mkdir(parents=True, exist_ok=True)

        for path in (
            self.workspace / "input",
            self.workspace / "analysis",
            self.workspace / "narration",
            self.workspace / "clips",
            self.workspace / "timeline",
            self.workspace / "output",
        ):
            path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def discover(cls, start: Path | None = None) -> "ProjectPaths":
        current = (start or Path.cwd()).resolve()

        for candidate in (current, *current.parents):
            if (candidate / "README.md").exists() and (
                candidate / "config"
            ).exists():
                return cls(candidate)

        return cls(current)
