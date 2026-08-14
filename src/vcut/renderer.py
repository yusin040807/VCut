from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

from .audit_log import append_event
from .exceptions import RenderError
from .ffmpeg_adapter import FFmpegAdapter
from .models import CameraSource, EDLSegment, Project, SubtitleEntry
from .subtitle_service import export_srt
from .validation import ValidationService, blocking


class Renderer:
    """Staged FFmpeg renderer; all processes use argument arrays and shell=False."""

    def __init__(self, adapter: FFmpegAdapter | None = None) -> None:
        self.adapter = adapter or FFmpegAdapter()

    def render(self, project_root: Path, project: Project, cameras: list[CameraSource], segments: list[EDLSegment], subtitles: list[SubtitleEntry] | None = None, *, preview: bool = False, progress: Callable[[str], None] | None = None) -> Path:
        validation = ValidationService()
        issues = validation.validate_preview(project, cameras, segments) if preview else validation.validate_final(project, cameras, segments, subtitles)
        if blocking(issues):
            summary = "; ".join(issue.message for issue in issues[:4])
            raise RenderError(f"Rendering is blocked: {summary}")
        self.adapter.require()
        project_root = project_root.resolve()
        work = project_root / "temp" / "render-work"
        work.mkdir(parents=True, exist_ok=True)
        for old in work.glob("segment-*.mp4"):
            old.unlink()
        camera_map = {camera.id: camera for camera in cameras}
        width, height = (854, 480) if preview else (project.render_settings.width, project.render_settings.height)
        clip_paths: list[Path] = []
        log_path = project_root / "logs" / "render.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_lines: list[str] = []
        try:
            for index, segment in enumerate(segments, 1):
                if progress:
                    progress(f"Rendering segment {index} of {len(segments)}")
                destination = work / f"segment-{index:04d}.mp4"
                command = self.adapter.segment_command(Path(camera_map[segment.selected_camera].file), destination, segment.source_start, segment.source_end - segment.source_start, width, height, project.render_settings.fps, preview)
                # Fade is applied to the visual clip without relying on shell parsing.
                if segment.transition == "fade":
                    vf_index = command.index("-vf") + 1
                    command[vf_index] += ",fade=t=in:st=0:d=0.6"
                result = self.adapter.run(command)
                log_lines.extend(["COMMAND: " + repr(command), result.stderr])
                clip_paths.append(destination)
            concat_file = work / "concat.txt"
            concat_file.write_text("".join(f"file '{path.as_posix().replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n" for path in clip_paths), encoding="utf-8")
            visual = work / "visual.mp4"
            concat_command = [self.adapter.require(), "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(visual)]
            result = self.adapter.run(concat_command)
            log_lines.extend(["COMMAND: " + repr(concat_command), result.stderr])
            if progress:
                progress("Adding continuous audio and text")
            output_dir = project_root / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            output = output_dir / ("preview.mp4" if preview else "final_video.mp4")
            candidate = work / output.name
            final_command = self._final_command(visual, candidate, project, cameras, segments, subtitles or [], preview, work)
            result = self.adapter.run(final_command)
            log_lines.extend(["COMMAND: " + repr(final_command), result.stderr])
            if not candidate.is_file() or candidate.stat().st_size == 0:
                raise RenderError("FFmpeg returned without creating a readable output file.")
            shutil.copy2(candidate, output)
            append_event(project_root, "preview_render" if preview else "final_render", output=str(output.relative_to(project_root)))
            return output
        except Exception as exc:
            append_event(project_root, "preview_render" if preview else "final_render", "failure", error=type(exc).__name__)
            raise
        finally:
            log_path.write_text("\n".join(log_lines), encoding="utf-8")

    def _final_command(self, visual: Path, destination: Path, project: Project, cameras: list[CameraSource], segments: list[EDLSegment], subtitles: list[SubtitleEntry], preview: bool, work: Path) -> list[str]:
        command = [self.adapter.require(), "-y", "-i", str(visual)]
        duration = max(item.timeline_end for item in segments) - min(item.timeline_start for item in segments)
        audio = next((camera for camera in cameras if camera.id == project.main_audio_camera and camera.has_audio), None)
        if audio:
            command.extend(["-ss", f"{min(item.timeline_start for item in segments):.3f}", "-i", audio.file])
        filters: list[str] = []
        if subtitles:
            subtitle_path = work / "subtitles.srt"
            subtitle_path.write_text(export_srt(subtitles), encoding="utf-8")
            escaped = subtitle_path.as_posix().replace(":", "\\:").replace("'", "\\'")
            filters.append(f"subtitles='{escaped}'")
        if project.opening_title:
            filters.append(f"drawtext=text='{self._escape(project.opening_title)}':x=(w-tw)/2:y=h*0.15:fontsize=38:fontcolor=white:box=1:boxcolor=black@0.5:enable='between(t,0,4)'")
        if project.lower_third:
            filters.append(f"drawtext=text='{self._escape(project.lower_third)}':x=40:y=h-th-42:fontsize=28:fontcolor=white:box=1:boxcolor=black@0.65:enable='between(t,{project.lower_third_start},{project.lower_third_end})'")
        if project.closing_credits:
            start = max(0, duration - 5)
            filters.append(f"drawtext=text='{self._escape(project.closing_credits)}':x=(w-tw)/2:y=(h-th)/2:fontsize=30:fontcolor=white:box=1:boxcolor=black@0.6:enable='between(t,{start:.3f},{duration:.3f})'")
        if filters:
            command.extend(["-vf", ",".join(filters)])
        if audio:
            volume = 0.0 if project.render_settings.muted else project.render_settings.volume
            audio_filter = f"volume={volume},afade=t=in:st=0:d={project.render_settings.fade_in},afade=t=out:st={max(0, duration-project.render_settings.fade_out)}:d={project.render_settings.fade_out}"
            command.extend(["-af", audio_filter, "-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac"])
        else:
            command.append("-an")
        command.extend(["-c:v", "libx264", "-preset", "veryfast" if preview else "medium", "-pix_fmt", "yuv420p", "-t", f"{duration:.3f}", "-movflags", "+faststart", str(destination)])
        return command

    @staticmethod
    def _escape(text: str) -> str:
        return (text.replace("\\", "\\\\").replace("'", "\\'")
                .replace(":", "\\:").replace("%", "\\%")
                .replace(",", "\\,").replace(";", "\\;")
                .replace("[", "\\[").replace("]", "\\]").replace("\n", "\\n"))
