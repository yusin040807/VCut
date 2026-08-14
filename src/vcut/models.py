from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RenderSettings:
    width: int = 1280
    height: int = 720
    fps: float = 30.0
    volume: float = 1.0
    muted: bool = False
    fade_in: float = 1.0
    fade_out: float = 1.0


@dataclass
class Project:
    project_name: str
    event_name: str = "Kindergarten Graduation Ceremony 2026"
    event_date: str = ""
    schema_version: str = "1.0"
    sharing_type: str = "private"
    consent_confirmed: bool = False
    opening_title: str = "Kindergarten Graduation Ceremony 2026"
    closing_credits: str = "Edited with VCut\nDeveloped for BTIS3053 Social & Professional Issues"
    lower_third: str = "Graduation Ceremony"
    lower_third_start: float = 5.0
    lower_third_end: float = 10.0
    main_audio_camera: str = ""
    status: str = "setup"
    privacy_confirmed: bool = False
    copyright_confirmed: bool = False
    render_settings: RenderSettings = field(default_factory=RenderSettings)


@dataclass
class CameraSource:
    id: str
    name: str
    role: str
    file: str
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    codec: str = ""
    has_audio: bool = False
    file_size: int = 0


@dataclass
class SynchronizationConfig:
    reference_camera_id: str
    clap_times: dict[str, float]
    offsets: dict[str, float]
    approved: bool = False


@dataclass
class ProgrammeSegment:
    id: str
    start: float
    end: float
    event_type: str
    description: str = ""


@dataclass
class Overlay:
    type: str = "none"
    text: str = ""


@dataclass
class EDLSegment:
    id: str
    timeline_start: float
    timeline_end: float
    selected_camera: str
    source_start: float
    source_end: float
    event_type: str
    description: str
    reason: str
    transition: str = "cut"
    overlay: Overlay = field(default_factory=Overlay)
    approved: bool = False
    manually_modified: bool = False


@dataclass
class SubtitleEntry:
    start: float
    end: float
    text: str
    source: str = "Manual"


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: str
    message: str
    segment_id: str | None = None
    field: str | None = None


@dataclass
class CameraRecommendation:
    camera_id: str
    reason: str


def to_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {key: to_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: to_dict(item) for key, item in value.items()}
    return value


def project_from_dict(data: dict[str, Any]) -> Project:
    values = dict(data)
    values["render_settings"] = RenderSettings(**values.get("render_settings", {}))
    return Project(**values)


def camera_from_dict(data: dict[str, Any]) -> CameraSource:
    return CameraSource(**data)


def overlay_from_dict(data: dict[str, Any] | None) -> Overlay:
    return Overlay(**(data or {}))


def edl_from_dict(data: dict[str, Any]) -> EDLSegment:
    values = dict(data)
    values["overlay"] = overlay_from_dict(values.get("overlay"))
    return EDLSegment(**values)


def subtitle_from_dict(data: dict[str, Any]) -> SubtitleEntry:
    return SubtitleEntry(**data)
