from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .exceptions import DependencyError, RenderError


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class FFmpegAdapter:
    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable or shutil.which("ffmpeg") or ""

    def require(self) -> str:
        if not self.executable:
            raise DependencyError("FFmpeg was not found. Install FFmpeg and add its bin folder to PATH before rendering.")
        return self.executable

    def segment_command(self, source: Path, destination: Path, start: float, duration: float, width: int, height: int, fps: float, preview: bool = False) -> list[str]:
        executable = self.require()
        filters = [f"scale={width}:{height}:force_original_aspect_ratio=decrease", f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2", f"fps={fps}", "format=yuv420p"]
        if preview:
            filters.append("drawtext=text='DRAFT PREVIEW':x=w-tw-24:y=24:fontsize=24:fontcolor=white@0.8:box=1:boxcolor=black@0.45")
        return [executable, "-y", "-ss", f"{start:.3f}", "-i", str(source), "-t", f"{duration:.3f}", "-vf", ",".join(filters), "-an", "-c:v", "libx264", "-preset", "veryfast" if preview else "medium", "-pix_fmt", "yuv420p", str(destination)]

    def run(self, command: list[str], timeout: int | None = None) -> CommandResult:
        result = subprocess.run(command, capture_output=True, text=True, shell=False, timeout=timeout)
        if result.returncode:
            raise RenderError("FFmpeg could not complete the requested render. See the project render log for details.")
        return CommandResult(result.returncode, result.stdout, result.stderr)
