from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .exceptions import DependencyError, MediaProbeError
from .models import CameraSource


def dependency_status() -> dict[str, bool | str]:
    return {
        "ffmpeg": shutil.which("ffmpeg") or False,
        "ffprobe": shutil.which("ffprobe") or False,
    }


def probe_media(path: Path, camera_id: str, name: str, role: str) -> CameraSource:
    executable = shutil.which("ffprobe")
    if not executable:
        raise DependencyError("ffprobe was not found. Install FFmpeg and add its bin folder to PATH.")
    if path.suffix.lower() != ".mp4" or not path.is_file():
        raise MediaProbeError("Choose an existing MP4 camera recording.")
    command = [executable, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]
    result = subprocess.run(command, capture_output=True, text=True, shell=False, timeout=60)
    if result.returncode:
        raise MediaProbeError("ffprobe could not inspect this recording. It may be unsupported or damaged.")
    try:
        data = json.loads(result.stdout)
        video = next(stream for stream in data["streams"] if stream.get("codec_type") == "video")
        rate = video.get("avg_frame_rate", "0/1").split("/")
        fps = float(rate[0]) / float(rate[1]) if float(rate[1]) else 0.0
        duration = float(data.get("format", {}).get("duration", video.get("duration", 0)))
        return CameraSource(camera_id, name, role, str(path.resolve()), duration, int(video.get("width", 0)), int(video.get("height", 0)), fps, video.get("codec_name", ""), any(s.get("codec_type") == "audio" for s in data["streams"]), path.stat().st_size)
    except (KeyError, StopIteration, TypeError, ValueError) as exc:
        raise MediaProbeError("This file does not contain a readable video stream.") from exc
