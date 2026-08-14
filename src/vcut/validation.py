from __future__ import annotations

from pathlib import Path

from .models import CameraSource, EDLSegment, Project, SubtitleEntry, ValidationIssue


class ValidationService:
    def validate_preview(self, project: Project, cameras: list[CameraSource], segments: list[EDLSegment]) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if not project.consent_confirmed:
            issues.append(self._issue("CONSENT_NOT_CONFIRMED", "error", "Confirm that the footage is authorized or simulated."))
        if len(cameras) < 2:
            issues.append(self._issue("CAMERA_COUNT_TOO_LOW", "error", "Add at least two cameras."))
        if len(cameras) > 4:
            issues.append(self._issue("CAMERA_COUNT_TOO_HIGH", "error", "VCut supports no more than four cameras."))
        camera_ids = {camera.id for camera in cameras}
        for camera in cameras:
            if not Path(camera.file).is_file():
                issues.append(self._issue("CAMERA_FILE_MISSING", "error", f"Replace the missing file for {camera.name}."))
        if not segments:
            issues.append(self._issue("EDL_EMPTY", "error", "Generate at least one EDL segment."))
        seen: set[str] = set()
        previous_end = -1.0
        for segment in segments:
            if segment.id in seen:
                issues.append(self._issue("SEGMENT_ID_DUPLICATE", "error", "Segment identifiers must be unique.", segment.id))
            seen.add(segment.id)
            if segment.timeline_start < previous_end:
                issues.append(self._issue("SEGMENT_OVERLAP", "error", "Segment overlaps the previous segment.", segment.id))
            previous_end = max(previous_end, segment.timeline_end)
            if segment.timeline_end <= segment.timeline_start:
                issues.append(self._issue("SEGMENT_RANGE_INVALID", "error", "Segment end must be later than start.", segment.id))
            if segment.selected_camera not in camera_ids:
                issues.append(self._issue("CAMERA_INVALID", "error", "Select an imported camera.", segment.id))
            camera = next((item for item in cameras if item.id == segment.selected_camera), None)
            if segment.source_start < 0 or (camera and camera.duration and segment.source_end > camera.duration + 0.05):
                issues.append(self._issue("SOURCE_RANGE_INVALID", "error", "Segment source time is outside the camera recording.", segment.id))
        if not project.main_audio_camera:
            issues.append(self._issue("MAIN_AUDIO_INVALID", "error", "Select a main audio camera."))
        elif project.main_audio_camera not in camera_ids:
            issues.append(self._issue("MAIN_AUDIO_INVALID", "error", "Select an imported camera as the main audio source."))
        elif project.main_audio_camera:
            audio = next(camera for camera in cameras if camera.id == project.main_audio_camera)
            if not audio.has_audio:
                issues.append(self._issue("MAIN_AUDIO_MISSING", "error", "The selected main audio camera has no audio stream."))
        return issues

    def validate_final(self, project: Project, cameras: list[CameraSource], segments: list[EDLSegment], subtitles: list[SubtitleEntry] | None = None) -> list[ValidationIssue]:
        issues = self.validate_preview(project, cameras, segments)
        duration = max((segment.timeline_end for segment in segments), default=0) - min((segment.timeline_start for segment in segments), default=0)
        if duration < 60 or duration > 180:
            issues.append(self._issue("OUTPUT_DURATION_INVALID", "error", "Final duration must be between 60 and 180 seconds."))
        used = [segment.selected_camera for segment in segments]
        switches = sum(left != right for left, right in zip(used, used[1:]))
        if len(set(used)) < 2:
            issues.append(self._issue("CAMERAS_USED_TOO_LOW", "error", "Use at least two camera angles."))
        if switches < 3:
            issues.append(self._issue("CAMERA_SWITCHES_TOO_LOW", "error", "Add at least three camera switches."))
        if not project.opening_title.strip():
            issues.append(self._issue("OPENING_TITLE_MISSING", "error", "Add an opening title."))
        if not project.closing_credits.strip():
            issues.append(self._issue("CLOSING_CREDITS_MISSING", "error", "Add closing credits."))
        if not project.lower_third.strip() and not subtitles:
            issues.append(self._issue("LABEL_OR_SUBTITLE_MISSING", "error", "Add a lower-third label or subtitle."))
        for index, subtitle in enumerate(subtitles or [], 1):
            if subtitle.start < 0 or subtitle.end <= subtitle.start or subtitle.end > duration + 0.05:
                issues.append(self._issue("SUBTITLE_RANGE_INVALID", "error", f"Correct the timing for subtitle {index}."))
            if not subtitle.text.strip():
                issues.append(self._issue("SUBTITLE_TEXT_EMPTY", "error", f"Add text to subtitle {index}."))
        ordered_subtitles = sorted(subtitles or [], key=lambda item: item.start)
        if any(left.end > right.start for left, right in zip(ordered_subtitles, ordered_subtitles[1:])):
            issues.append(self._issue("SUBTITLE_OVERLAP", "warning", "Some subtitles overlap; review their timing."))
        if not any(segment.transition == "fade" for segment in segments):
            issues.append(self._issue("TRANSITION_MISSING", "error", "Add at least one fade transition."))
        for segment in segments:
            if not segment.approved:
                issues.append(self._issue("SEGMENT_NOT_APPROVED", "error", "Review and approve this segment.", segment.id))
        if not project.privacy_confirmed:
            issues.append(self._issue("PRIVACY_NOT_CONFIRMED", "error", "Complete the final privacy check."))
        if not project.copyright_confirmed:
            issues.append(self._issue("COPYRIGHT_NOT_CONFIRMED", "error", "Complete the final copyright check."))
        return issues

    @staticmethod
    def _issue(code: str, severity: str, message: str, segment_id: str | None = None) -> ValidationIssue:
        return ValidationIssue(code, severity, message, segment_id)


def blocking(issues: list[ValidationIssue]) -> bool:
    return any(issue.severity == "error" for issue in issues)
