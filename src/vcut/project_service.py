from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .exceptions import ProjectError
from .models import CameraSource, Project, camera_from_dict, project_from_dict, to_dict

PROJECT_DIRS = ("source", "subtitles", "temp/segments", "temp/render-work", "output", "logs", "evidence/screenshots")


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    json.loads(temporary.read_text(encoding="utf-8"))
    os.replace(temporary, path)


class ProjectService:
    def create_project(self, root: Path, project: Project) -> Path:
        root = root.resolve()
        if not project.project_name.strip():
            raise ProjectError("Project name is required.")
        root.mkdir(parents=True, exist_ok=True)
        if (root / "project.json").exists():
            raise ProjectError("A VCut project already exists in this folder.")
        for relative in PROJECT_DIRS:
            (root / relative).mkdir(parents=True, exist_ok=True)
        self.save_project(root, project)
        self.save_cameras(root, [])
        return root

    def save_project(self, root: Path, project: Project) -> None:
        atomic_write_json(root.resolve() / "project.json", to_dict(project))

    def load_project(self, root: Path) -> Project:
        path = root.resolve() / "project.json"
        try:
            return project_from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError) as exc:
            raise ProjectError(f"Could not open this VCut project: {exc}") from exc

    def save_cameras(self, root: Path, cameras: list[CameraSource]) -> None:
        atomic_write_json(root.resolve() / "cameras.json", [to_dict(camera) for camera in cameras])

    def load_cameras(self, root: Path) -> list[CameraSource]:
        path = root.resolve() / "cameras.json"
        if not path.exists():
            return []
        try:
            return [camera_from_dict(item) for item in json.loads(path.read_text(encoding="utf-8"))]
        except (OSError, ValueError, TypeError) as exc:
            raise ProjectError(f"Could not read camera data: {exc}") from exc

    @staticmethod
    def safe_project_path(root: Path, relative: str) -> Path:
        root = root.resolve()
        candidate = (root / relative).resolve()
        if candidate != root and root not in candidate.parents:
            raise ProjectError("The requested path is outside the active project.")
        return candidate
