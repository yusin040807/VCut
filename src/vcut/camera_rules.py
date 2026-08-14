# from __future__ import annotations

# from .exceptions import EDLValidationError
# from .models import CameraRecommendation, CameraSource, ProgrammeSegment

# PREFERENCES = {
#     "opening": ["wide", "side", "front", "front_left", "front_right"],
#     "speech": ["front_left", "front_right", "front", "side", "wide"],
#     "performance": ["wide", "side", "front", "front_left", "front_right"],
#     "graduation": ["front_right", "front_left", "front", "side", "wide"],
#     "audience": ["side", "wide", "front", "front_left", "front_right"],
#     "closing": ["wide", "side", "front", "front_left", "front_right"],
# }


# def _normalized_role(role: str) -> str:
#     return role.strip().lower().replace("-", "_").replace(" ", "_")


# def recommend_camera(segment: ProgrammeSegment, cameras: list[CameraSource], previous_camera_id: str | None = None) -> CameraRecommendation:
#     available = [camera for camera in cameras if camera.file]
#     if not available:
#         raise EDLValidationError("No available camera can be recommended.")
#     preferences = PREFERENCES.get(segment.event_type.lower(), ["wide", "front", "side", "front_left", "front_right"])
#     ranked = sorted(available, key=lambda camera: (preferences.index(_normalized_role(camera.role)) if _normalized_role(camera.role) in preferences else len(preferences), camera.id))
#     selected = ranked[0]
#     # If the same view would dominate, use the next suitable camera on a long segment.
#     if selected.id == previous_camera_id and segment.end - segment.start >= 8 and len(ranked) > 1:
#         selected = ranked[1]
#         reason = f"{selected.name} provides visual variety at this segment boundary while remaining suitable for {segment.event_type}."
#     else:
#         role = selected.role.replace("_", " ").replace("-", " ")
#         reason = f"{selected.name} was selected because its {role} view is preferred for {segment.event_type}."
#     return CameraRecommendation(selected.id, reason)

from __future__ import annotations

from typing import Any

from .exceptions import EDLValidationError
from .models import (
    CameraRecommendation,
    CameraSource,
    ProgrammeSegment,
    SynchronizationConfig,
)


# ============================================================
# Camera role preferences
# ============================================================
#
# These are NOT hard rules.
# They are only BASE preferences.
#
# Later, vision analysis can add scores for:
# - person detection
# - subject size
# - composition
# - sharpness
# - motion
#
# Example:
#
#   performance:
#       wide      = useful for group performance
#       front     = useful for main subject
#       side      = useful for movement
#
# ============================================================

PREFERENCES: dict[str, list[str]] = {
    "opening": [
        "wide",
        "front",
        "side",
        "front_left",
        "front_right",
    ],
    "speech": [
        "front",
        "front_left",
        "front_right",
        "side",
        "wide",
    ],
    "performance": [
        "front",
        "wide",
        "side",
        "front_left",
        "front_right",
    ],
    "graduation": [
        "front",
        "front_left",
        "front_right",
        "wide",
        "side",
    ],
    "audience": [
        "wide",
        "side",
        "front",
        "front_left",
        "front_right",
    ],
    "closing": [
        "wide",
        "front",
        "side",
        "front_left",
        "front_right",
    ],
}


# ============================================================
# Configuration
# ============================================================

# How much the previous camera is protected from unnecessary
# re-selection.
#
# This does NOT force a switch.
# It only prevents the exact same camera from getting an
# artificial advantage when another camera is equally suitable.
PREVIOUS_CAMERA_PENALTY = 2.0


# If two cameras are nearly identical, keep the current camera.
#
# This is useful later for automatic switching.
SWITCH_MARGIN = 0.08


# Prefer cameras that have a valid recording range.
AVAILABILITY_SCORE = 10.0


# Role score range.
ROLE_SCORE_STEP = 1.0


# ============================================================
# Utility functions
# ============================================================

def _normalized_role(role: str) -> str:
    """
    Normalize camera role names.

    Examples:
        "front-left"  -> "front_left"
        "Front Left"  -> "front_left"
        " WIDE "      -> "wide"
    """
    return (
        (role or "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )


def _normalized_event_type(event_type: str) -> str:
    """
    Normalize programme event type.
    """
    return (event_type or "").strip().lower().replace("-", "_").replace(" ", "_")


def _preference_list(event_type: str) -> list[str]:
    """
    Return the preferred camera roles for an event.
    """
    event = _normalized_event_type(event_type)

    return PREFERENCES.get(
        event,
        [
            "front",
            "wide",
            "side",
            "front_left",
            "front_right",
        ],
    )


def _role_score(role: str, preferences: list[str]) -> float:
    """
    Convert role preference into a numeric score.

    Higher is better.

    Example:
        preferences =
            ["front", "wide", "side"]

        front -> 3
        wide  -> 2
        side  -> 1
        unknown -> 0
    """
    normalized = _normalized_role(role)

    if normalized not in preferences:
        return 0.0

    index = preferences.index(normalized)

    return float(len(preferences) - index) * ROLE_SCORE_STEP


# ============================================================
# Camera source range / synchronization
# ============================================================

def timeline_to_source_range(
    camera: CameraSource,
    timeline_start: float,
    timeline_end: float,
    synchronization: SynchronizationConfig | None,
) -> tuple[float, float]:
    """
    Convert a timeline range to the camera's source range.

    Synchronization offsets in this project follow:

        source_time = timeline_time + offset

    Example:

        CAM001 offset = 0
        CAM002 offset = -57

        timeline = 57

        CAM002 source = 57 + (-57)
                      = 0

    Returns:
        (source_start, source_end)
    """

    if timeline_end <= timeline_start:
        raise EDLValidationError(
            "Timeline end must be later than timeline start."
        )

    if synchronization is None:
        # Backward-compatible mode.
        # If no synchronization is provided, assume timeline and
        # source time are identical.
        return float(timeline_start), float(timeline_end)

    if camera.id not in synchronization.offsets:
        raise EDLValidationError(
            f"Camera {camera.id} has no synchronization offset."
        )

    offset = synchronization.offsets[camera.id]

    source_start = timeline_start + offset
    source_end = timeline_end + offset

    return round(source_start, 6), round(source_end, 6)


def camera_is_available(
    camera: CameraSource,
    timeline_start: float,
    timeline_end: float,
    synchronization: SynchronizationConfig | None = None,
    tolerance: float = 0.05,
) -> bool:
    """
    Check whether the COMPLETE timeline segment can be supplied
    by this camera.

    This is important.

    Example:

        CAM002 becomes available at timeline 57s.

        Segment:
            40s -> 70s

        CAM002 is NOT valid for the entire segment because
        its source range would start before 0s.

    Therefore this function returns False.

    A later EDL service can split the programme segment at
    camera availability boundaries.
    """

    if not camera.file:
        return False

    if timeline_end <= timeline_start:
        return False

    try:
        source_start, source_end = timeline_to_source_range(
            camera,
            timeline_start,
            timeline_end,
            synchronization,
        )
    except EDLValidationError:
        return False

    # Source cannot start before the physical recording.
    if source_start < -tolerance:
        return False

    # If duration is known, source cannot extend beyond it.
    if camera.duration > 0:
        if source_end > camera.duration + tolerance:
            return False

    return True


def get_available_cameras(
    cameras: list[CameraSource],
    timeline_start: float,
    timeline_end: float,
    synchronization: SynchronizationConfig | None = None,
) -> list[CameraSource]:
    """
    Return only cameras that can legally cover the COMPLETE
    requested timeline range.
    """

    return [
        camera
        for camera in cameras
        if camera_is_available(
            camera,
            timeline_start,
            timeline_end,
            synchronization,
        )
    ]


# ============================================================
# Camera scoring
# ============================================================

def score_camera_role(
    camera: CameraSource,
    event_type: str,
) -> float:
    """
    Score a camera based on its role and event type.

    This is the rule-based BASE score.

    It is deliberately kept separate from vision scoring so
    that a future VisionAnalyzer can add:

        vision_score

    without rewriting this module.
    """

    preferences = _preference_list(event_type)

    return _role_score(
        camera.role,
        preferences,
    )


def score_camera(
    camera: CameraSource,
    event_type: str,
    previous_camera_id: str | None = None,
    vision_score: float | None = None,
) -> float:
    """
    Calculate the current camera score.

    Components:

        role score
        +
        optional vision score
        -
        small previous-camera penalty

    vision_score is optional because the VisionAnalyzer will be
    added later.

    Expected vision_score range:
        0.0 - 100.0

    The rule-based score is intentionally modest compared with
    the future vision score.
    """

    score = score_camera_role(
        camera,
        event_type,
    )

    # --------------------------------------------------------
    # Optional Vision AI score
    # --------------------------------------------------------
    #
    # When vision_score is supplied, it becomes the main
    # decision factor.
    #
    # Example:
    #
    #   CAM001 vision = 52
    #   CAM002 vision = 91
    #   CAM003 vision = 67
    #   CAM004 vision = 81
    #
    # Then CAM002 can beat the role preference.
    #
    if vision_score is not None:
        # Normalize expected vision score into 0-10 range.
        normalized_vision = max(
            0.0,
            min(float(vision_score), 100.0),
        ) / 10.0

        # Vision should have much more influence than role.
        score += normalized_vision * 3.0

    # --------------------------------------------------------
    # Previous camera penalty
    # --------------------------------------------------------
    #
    # This prevents the previous camera from receiving an
    # artificial advantage.
    #
    # It does NOT force a camera switch.
    #
    if previous_camera_id == camera.id:
        score -= PREVIOUS_CAMERA_PENALTY

    return score


# ============================================================
# Camera recommendation
# ============================================================

def recommend_camera(
    segment: ProgrammeSegment,
    cameras: list[CameraSource],
    previous_camera_id: str | None = None,
    synchronization: SynchronizationConfig | None = None,
    vision_scores: dict[str, float] | None = None,
) -> CameraRecommendation:
    """
    Recommend the best camera for one programme segment.

    Parameters
    ----------
    segment:
        Programme segment being evaluated.

    cameras:
        Imported camera sources.

    previous_camera_id:
        Camera selected for the previous EDL segment.

    synchronization:
        Synchronization configuration.

        IMPORTANT:
        Pass this when source-range validation is required.

    vision_scores:
        Optional camera vision scores.

        Example:

            {
                "CAM001": 52.4,
                "CAM002": 91.2,
                "CAM003": 67.8,
                "CAM004": 84.1,
            }

        These scores can come from VisionAnalyzer.

    Returns
    -------
    CameraRecommendation
    """

    if not cameras:
        raise EDLValidationError(
            "No cameras were imported."
        )

    # --------------------------------------------------------
    # 1. Find cameras that can legally cover the segment
    # --------------------------------------------------------

    available = get_available_cameras(
        cameras=cameras,
        timeline_start=segment.start,
        timeline_end=segment.end,
        synchronization=synchronization,
    )

    if not available:
        raise EDLValidationError(
            f"No camera can cover timeline "
            f"{segment.start:.3f}s–{segment.end:.3f}s "
            f"for programme segment {segment.id}."
        )

    # --------------------------------------------------------
    # 2. Score every available camera
    # --------------------------------------------------------

    vision_scores = vision_scores or {}

    scored: list[tuple[CameraSource, float]] = []

    for camera in available:
        score = score_camera(
            camera=camera,
            event_type=segment.event_type,
            previous_camera_id=previous_camera_id,
            vision_score=vision_scores.get(camera.id),
        )

        scored.append(
            (camera, score)
        )

    # --------------------------------------------------------
    # 3. Sort by score
    #
    # Stable secondary sorting by camera ID makes results
    # deterministic.
    # --------------------------------------------------------

    scored.sort(
        key=lambda item: (
            -item[1],
            item[0].id,
        )
    )

    selected_camera, selected_score = scored[0]

    # --------------------------------------------------------
    # 4. Build explanation
    # --------------------------------------------------------

    role = (
        _normalized_role(selected_camera.role)
        .replace("_", " ")
    )

    reason_parts = [
        f"{selected_camera.name} was selected",
        f"because its {role} view is preferred for "
        f"{segment.event_type}, providing variety "
        f"from the previous camera view",
        ]

    # Include vision explanation when available.
    if selected_camera.id in vision_scores:
        vision_value = vision_scores[selected_camera.id]

        reason_parts.append(
            f"with a vision score of {vision_value:.1f}"
        )

    # Mention previous camera when relevant.
    if selected_camera.id == previous_camera_id:
        reason_parts.append(
            "while avoiding an unnecessary camera change"
        )

    # Explain availability.
    if synchronization is not None:
        source_start, source_end = timeline_to_source_range(
            selected_camera,
            segment.start,
            segment.end,
            synchronization,
        )

        reason_parts.append(
            f"(source {source_start:.3f}s–{source_end:.3f}s)"
        )

    reason = " ".join(reason_parts) + "."

    return CameraRecommendation(
        selected_camera.id,
        reason,
    )


# ============================================================
# Automatic switching helper
# ============================================================

def should_switch_camera(
    current_camera_id: str,
    candidate_camera_id: str,
    current_score: float,
    candidate_score: float,
    minimum_margin: float = SWITCH_MARGIN,
) -> bool:
    """
    Decide whether a new camera is sufficiently better than
    the current camera to justify a switch.

    This prevents unnecessary:

        C4 -> C2 -> C4 -> C2

    switching.

    Example:

        current = 8.2
        candidate = 8.5

        difference = 0.3

        if minimum_margin = 0.8:
            KEEP current camera.

    But:

        current = 7.0
        candidate = 9.1

        difference = 2.1

        -> SWITCH.
    """

    if current_camera_id == candidate_camera_id:
        return False

    improvement = candidate_score - current_score

    return improvement >= minimum_margin


# ============================================================
# Utility for future VisionAnalyzer
# ============================================================

def rank_cameras(
    segment: ProgrammeSegment,
    cameras: list[CameraSource],
    previous_camera_id: str | None = None,
    synchronization: SynchronizationConfig | None = None,
    vision_scores: dict[str, float] | None = None,
) -> list[tuple[str, float]]:
    """
    Return all valid cameras ranked from best to worst.

    This is useful for the future automatic editing engine.

    Example return:

        [
            ("CAM002", 11.8),
            ("CAM004", 10.4),
            ("CAM003", 8.7),
            ("CAM001", 7.9),
        ]

    The EDL service can then decide whether the top camera is
    sufficiently better than the current camera.
    """

    available = get_available_cameras(
        cameras=cameras,
        timeline_start=segment.start,
        timeline_end=segment.end,
        synchronization=synchronization,
    )

    if not available:
        raise EDLValidationError(
            f"No camera is available for "
            f"{segment.start:.3f}s–{segment.end:.3f}s."
        )

    vision_scores = vision_scores or {}

    ranked: list[tuple[str, float]] = []

    for camera in available:
        score = score_camera(
            camera=camera,
            event_type=segment.event_type,
            previous_camera_id=previous_camera_id,
            vision_score=vision_scores.get(camera.id),
        )

        ranked.append(
            (camera.id, score)
        )

    ranked.sort(
        key=lambda item: (
            -item[1],
            item[0],
        )
    )

    return ranked


# ============================================================
# Debug helper
# ============================================================

def explain_camera_availability(
    cameras: list[CameraSource],
    timeline_start: float,
    timeline_end: float,
    synchronization: SynchronizationConfig | None,
) -> dict[str, dict[str, Any]]:
    """
    Return a detailed diagnostic table.

    This is especially useful for debugging SOURCE_RANGE_INVALID.

    Example:

        {
            "CAM001": {
                "available": True,
                "source_start": 57.0,
                "source_end": 100.0,
                "duration": 125.1,
            },

            "CAM002": {
                "available": True,
                "source_start": 0.0,
                "source_end": 43.0,
                "duration": 43.05,
            },
        }
    """

    result: dict[str, dict[str, Any]] = {}

    for camera in cameras:
        try:
            source_start, source_end = timeline_to_source_range(
                camera,
                timeline_start,
                timeline_end,
                synchronization,
            )

            available = camera_is_available(
                camera,
                timeline_start,
                timeline_end,
                synchronization,
            )

            result[camera.id] = {
                "available": available,
                "source_start": source_start,
                "source_end": source_end,
                "duration": camera.duration,
                "role": camera.role,
            }

        except EDLValidationError as exc:
            result[camera.id] = {
                "available": False,
                "source_start": None,
                "source_end": None,
                "duration": camera.duration,
                "role": camera.role,
                "error": str(exc),
            }

    return result
