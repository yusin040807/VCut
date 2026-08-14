from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .models import CameraSource, SynchronizationConfig
from .synchronization import SynchronizationService


# ============================================================
# Configuration
# ============================================================

# YOLO model.
#
# yolo11n.pt is small and relatively fast.
#
# If your Ultralytics installation does not have this model
# available, you can use:
#
#     yolov8n.pt
#
# instead.
DEFAULT_MODEL = "yolo11n.pt"


# COCO class ID for "person".
PERSON_CLASS_ID = 0


# Minimum YOLO confidence.
PERSON_CONFIDENCE = 0.35


# Maximum number of frames used for motion estimation.
#
# We compare the current frame against a previous frame.
MAX_MOTION_FRAME_GAP = 2.0


# ============================================================
# Score weights
# ============================================================

# These weights should add up to 1.0.

WEIGHT_SUBJECT_SIZE   = 0.20
WEIGHT_SUBJECT_CENTER = 0.15
WEIGHT_PERSON_COUNT   = 0.15
WEIGHT_SHARPNESS      = 0.20
WEIGHT_MOTION         = 0.10
WEIGHT_ROLE           = 0.20


# ============================================================
# Data classes
# ============================================================


@dataclass
class PersonDetection:
    """
    Information about one detected person.
    """

    x1: float
    y1: float
    x2: float
    y2: float

    confidence: float

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center_x(self) -> float:
        return (self.x1 + self.x2) / 2.0

    @property
    def center_y(self) -> float:
        return (self.y1 + self.y2) / 2.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FrameAnalysis:
    """
    Analysis result for one frame.
    """

    camera_id: str
    source_time: float

    width: int
    height: int

    person_count: int

    persons: list[PersonDetection]

    main_subject_area_ratio: float
    main_subject_center_score: float

    person_count_score: float
    sharpness_score: float
    motion_score: float

    role_score: float

    total_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "source_time": self.source_time,
            "width": self.width,
            "height": self.height,
            "person_count": self.person_count,
            "persons": [
                person.to_dict()
                for person in self.persons
            ],
            "main_subject_area_ratio": self.main_subject_area_ratio,
            "main_subject_center_score": self.main_subject_center_score,
            "person_count_score": self.person_count_score,
            "sharpness_score": self.sharpness_score,
            "motion_score": self.motion_score,
            "role_score": self.role_score,
            "total_score": self.total_score,
        }


# ============================================================
# Vision Analyzer
# ============================================================


class VisionAnalyzer:
    """
    Analyze synchronized camera frames.

    The analyzer compares Camera 1/2/3/4 at the SAME timeline
    moment.

    Example:

        timeline = 65.0

        CAM001 source = 65.0
        CAM002 source = 8.0
        CAM003 source = 57.0
        CAM004 source = 47.0

    Each frame is analyzed independently.

    The result can then be used by camera_rules.py to choose
    the best camera.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        person_confidence: float = PERSON_CONFIDENCE,
    ) -> None:

        self.model_name = model_name
        self.person_confidence = person_confidence

        self._model = None

        # Previous frames used for motion analysis.
        #
        # camera_id -> grayscale frame
        self._previous_frames: dict[str, np.ndarray] = {}

        self._previous_times: dict[str, float] = {}

        self._captures: dict[str, cv2.VideoCapture] = {}
    # ========================================================
    # Lazy-load YOLO
    # ========================================================
    def close(self) -> None:
        """
        Release all open video captures.
        """

        for capture in self._captures.values():

            try:
                capture.release()

            except Exception:
                pass

        self._captures.clear()

        self._previous_frames.clear()

        self._previous_times.clear()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _get_model(self):
        """
        Load YOLO only when it is actually needed.

        This avoids loading a large model when VCut starts
        without performing video analysis.
        """

        if self._model is None:

            try:
                from ultralytics import YOLO
            except ImportError as exc:
                raise RuntimeError(
                    "Ultralytics is not installed. "
                    "Run: pip install ultralytics"
                ) from exc

            self._model = YOLO(
                self.model_name
            )

        return self._model

    # ========================================================
    # Open video
    # ========================================================

    @staticmethod
    def _open_video(
        camera: CameraSource,
    ) -> cv2.VideoCapture:
        """
        Open a camera video file.
        """

        if not camera.file:
            raise ValueError(
                f"Camera {camera.id} has no video file."
            )

        path = Path(camera.file)

        if not path.exists():
            raise FileNotFoundError(
                f"Camera {camera.id} video not found: "
                f"{camera.file}"
            )

        capture = cv2.VideoCapture(
            str(path)
        )

        if not capture.isOpened():
            raise RuntimeError(
                f"Unable to open video for "
                f"{camera.id}: {camera.file}"
            )

        return capture

    # ========================================================
    # Read frame
    # ========================================================

    # def read_frame(
    #     self,
    #     camera: CameraSource,
    #     source_time: float,
    # ) -> np.ndarray:
    #     """
    #     Read one frame at a source timestamp.

    #     source_time is the time inside the ORIGINAL camera file,
    #     not the synchronized timeline.
    #     """

    #     if source_time < 0:
    #         raise ValueError(
    #             f"source_time cannot be negative: "
    #             f"{source_time}"
    #         )

    #     if camera.duration > 0:
    #         if source_time > camera.duration:
    #             raise ValueError(
    #                 f"source_time {source_time:.3f}s is outside "
    #                 f"{camera.id} duration "
    #                 f"{camera.duration:.3f}s."
    #             )

    #     capture = self._open_video(
    #         camera
    #     )

    #     try:
    #         capture.set(
    #             cv2.CAP_PROP_POS_MSEC,
    #             source_time * 1000.0,
    #         )

    #         success, frame = capture.read()

    #         if not success or frame is None:
    #             raise RuntimeError(
    #                 f"Unable to read frame from "
    #                 f"{camera.id} at "
    #                 f"{source_time:.3f}s."
    #             )

    #         return frame

    #     finally:
    #         capture.release()

    def read_frame(
    self,
    camera: CameraSource,
    source_time: float,
    ) -> np.ndarray:
        """
        Read one frame from a reusable VideoCapture.

        The VideoCapture stays open while VisionAnalyzer is running.
        This is much faster than opening and closing the MP4 for
        every frame.
        """

        if source_time < 0:
            raise ValueError(
                f"source_time cannot be negative: "
                f"{source_time}"
            )

        if camera.duration > 0:

            if source_time > camera.duration:

                raise ValueError(
                    f"source_time {source_time:.3f}s is outside "
                    f"{camera.id} duration "
                    f"{camera.duration:.3f}s."
                )

        # --------------------------------------------------------
        # Reuse existing capture
        # --------------------------------------------------------

        capture = self._captures.get(
            camera.id
        )

        # --------------------------------------------------------
        # Open only once
        # --------------------------------------------------------

        if (
            capture is None
            or not capture.isOpened()
        ):

            capture = self._open_video(
                camera
            )

            self._captures[
                camera.id
            ] = capture

    # --------------------------------------------------------
    # Seek to source timestamp
    # --------------------------------------------------------

        capture.set(
            cv2.CAP_PROP_POS_MSEC,
            source_time * 1000.0,
        )

        success, frame = capture.read()

        if (
            not success
            or frame is None
        ):

            raise RuntimeError(
                f"Unable to read frame from "
                f"{camera.id} at "
                f"{source_time:.3f}s."
            )

        return frame

    # ========================================================
    # Person detection
    # ========================================================

    def detect_persons(
        self,
        frame: np.ndarray,
    ) -> list[PersonDetection]:
        """
        Detect people using YOLO.

        Returns bounding boxes for class "person".
        """

        model = self._get_model()

        results = model.predict(
            source=frame,
            verbose=False,
            conf=self.person_confidence,
        )

        if not results:
            return []

        result = results[0]

        if result.boxes is None:
            return []

        detections: list[PersonDetection] = []

        boxes = result.boxes

        for index in range(
            len(boxes)
        ):

            class_id = int(
                boxes.cls[index].item()
            )

            if class_id != PERSON_CLASS_ID:
                continue

            confidence = float(
                boxes.conf[index].item()
            )

            x1, y1, x2, y2 = (
                boxes.xyxy[index]
                .tolist()
            )

            detections.append(
                PersonDetection(
                    x1=float(x1),
                    y1=float(y1),
                    x2=float(x2),
                    y2=float(y2),
                    confidence=confidence,
                )
            )

        return detections

    # ========================================================
    # Subject size
    # ========================================================

    @staticmethod
    def calculate_subject_size_score(
        persons: list[PersonDetection],
        frame_width: int,
        frame_height: int,
    ) -> tuple[float, float]:
        """
        Calculate:

            1. Main subject area ratio
            2. Normalized subject-size score

        The largest detected person is treated as the main
        subject.

        Example:

            small person:
                area = 5% of frame

            large person:
                area = 30% of frame

        Larger is generally better for close-up/detail shots,
        but the final decision also considers role and person
        count.
        """

        if not persons:
            return 0.0, 0.0

        frame_area = float(
            frame_width * frame_height
        )

        if frame_area <= 0:
            return 0.0, 0.0

        largest = max(
            persons,
            key=lambda person: person.area,
        )

        area_ratio = (
            largest.area / frame_area
        )

        # We treat 35% of the frame as an excellent main-subject
        # size for a general-purpose camera score.
        #
        # Anything above that is capped.
        score = min(
            area_ratio / 0.35,
            1.0,
        )

        return (
            area_ratio,
            score,
        )

    # ========================================================
    # Subject center score
    # ========================================================

    @staticmethod
    def calculate_subject_center_score(
        persons: list[PersonDetection],
        frame_width: int,
        frame_height: int,
    ) -> float:
        """
        Score how close the main person's center is to the
        center of the frame.

        Center = 1.0
        Edge   = 0.0
        """

        if not persons:
            return 0.0

        if frame_width <= 0 or frame_height <= 0:
            return 0.0

        main_subject = max(
            persons,
            key=lambda person: person.area,
        )

        subject_x = (
            main_subject.center_x
            / frame_width
        )

        subject_y = (
            main_subject.center_y
            / frame_height
        )

        distance = np.sqrt(
            (
                subject_x - 0.5
            ) ** 2
            +
            (
                subject_y - 0.5
            ) ** 2
        )

        # Maximum relevant distance is the corner distance.
        max_distance = np.sqrt(
            0.5 ** 2
            +
            0.5 ** 2
        )

        score = (
            1.0
            -
            (
                distance
                / max_distance
            )
        )

        return float(
            max(
                0.0,
                min(
                    score,
                    1.0,
                ),
            )
        )

    # ========================================================
    # Person count score
    # ========================================================

    @staticmethod
    def calculate_person_count_score(
        person_count: int,
    ) -> float:
        """
        Convert person count into a normalized score.

        This prevents a frame containing 20 people from
        automatically winning over a frame containing the main
        subject.

        The score peaks around 4 people.

        This can later be changed according to event type.
        """

        if person_count <= 0:
            return 0.0

        if person_count >= 4:
            return 1.0

        return person_count / 4.0

    # ========================================================
    # Sharpness
    # ========================================================

    @staticmethod
    def calculate_sharpness_score(
        frame: np.ndarray,
    ) -> float:
        """
        Calculate image sharpness using Laplacian variance.

        Higher variance generally means more visible edges
        and a sharper image.

        The result is normalized to 0-1.
        """

        if frame is None:
            return 0.0

        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY,
        )

        variance = float(
            cv2.Laplacian(
                gray,
                cv2.CV_64F,
            ).var()
        )

        # 500 is treated as a strong sharpness score.
        score = min(
            variance / 500.0,
            1.0,
        )

        return float(score)

    # ========================================================
    # Motion
    # ========================================================

    def calculate_motion_score(
        self,
        camera_id: str,
        frame: np.ndarray,
        source_time: float,
    ) -> float:
        """
        Estimate motion by comparing the current grayscale
        frame with the previous analyzed frame.

        This is NOT full optical flow.

        It is intentionally lightweight so that it can be used
        for a first version of automatic camera selection.
        """

        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY,
        )

        previous = self._previous_frames.get(
            camera_id
        )

        previous_time = self._previous_times.get(
            camera_id
        )

        self._previous_frames[
            camera_id
        ] = gray

        self._previous_times[
            camera_id
        ] = source_time

        if previous is None:
            return 0.0

        if previous_time is not None:
            if (
                abs(source_time - previous_time)
                > MAX_MOTION_FRAME_GAP
            ):
                return 0.0

        # Resize for faster comparison.
        small_current = cv2.resize(
            gray,
            (320, 180),
        )

        small_previous = cv2.resize(
            previous,
            (320, 180),
        )

        difference = cv2.absdiff(
            small_current,
            small_previous,
        )

        mean_difference = float(
            difference.mean()
        )

        # Empirical normalization.
        score = min(
            mean_difference / 35.0,
            1.0,
        )

        return float(score)

    # ========================================================
    # Camera role score
    # ========================================================

    @staticmethod
    def calculate_role_score(
        camera: CameraSource,
        person_count: int,
        main_subject_area_ratio: float,
    ) -> float:
        """
        Small role-based prior.

        IMPORTANT:

        Role is only a small component of the final score.

        It should NOT override actual video evidence.
        """

        role = (
            camera.role
            .strip()
            .lower()
            .replace("-", "_")
            .replace(" ", "_")
        )

        # No people detected.
        if person_count == 0:
            if role == "wide":
                return 1.0

            return 0.4

        # Close/large subject.
        if main_subject_area_ratio >= 0.20:

            if role == "front":
                return 1.0

            if role == "front_left":
                return 0.9

            if role == "front_right":
                return 0.9

            if role == "side":
                return 0.75

            if role == "wide":
                return 0.55

        # Group scene.
        if person_count >= 4:

            if role == "wide":
                return 1.0

            if role == "front":
                return 0.9

            if role == "side":
                return 0.85

            return 0.75

        # General scene.
        if role == "front":
            return 0.9

        if role == "wide":
            return 0.85

        if role == "side":
            return 0.8

        return 0.75

    # ========================================================
    # Total score
    # ========================================================

    @staticmethod
    def calculate_total_score(
        subject_size_score: float,
        subject_center_score: float,
        person_count_score: float,
        sharpness_score: float,
        motion_score: float,
        role_score: float,
    ) -> float:
        """
        Combine all visual features into a 0-100 score.
        """

        score = (
            WEIGHT_SUBJECT_SIZE
            * subject_size_score
            +
            WEIGHT_SUBJECT_CENTER
            * subject_center_score
            +
            WEIGHT_PERSON_COUNT
            * person_count_score
            +
            WEIGHT_SHARPNESS
            * sharpness_score
            +
            WEIGHT_MOTION
            * motion_score
            +
            WEIGHT_ROLE
            * role_score
        )

        return round(
            score * 100.0,
            2,
        )

    # ========================================================
    # Analyze one camera at one source time
    # ========================================================

    def analyze_camera(
        self,
        camera: CameraSource,
        source_time: float,
    ) -> FrameAnalysis:
        """
        Analyze one camera at one SOURCE timestamp.
        """

        frame = self.read_frame(
            camera,
            source_time,
        )

        height, width = frame.shape[:2]

        persons = self.detect_persons(
            frame
        )

        (
            main_subject_area_ratio,
            subject_size_score,
        ) = self.calculate_subject_size_score(
            persons,
            width,
            height,
        )

        subject_center_score = (
            self.calculate_subject_center_score(
                persons,
                width,
                height,
            )
        )

        person_count = len(
            persons
        )

        person_count_score = (
            self.calculate_person_count_score(
                person_count
            )
        )

        sharpness_score = (
            self.calculate_sharpness_score(
                frame
            )
        )

        motion_score = (
            self.calculate_motion_score(
                camera.id,
                frame,
                source_time,
            )
        )

        role_score = (
            self.calculate_role_score(
                camera,
                person_count,
                main_subject_area_ratio,
            )
        )

        total_score = (
            self.calculate_total_score(
                subject_size_score,
                subject_center_score,
                person_count_score,
                sharpness_score,
                motion_score,
                role_score,
            )
        )

        return FrameAnalysis(
            camera_id=camera.id,
            source_time=round(
                source_time,
                6,
            ),
            width=width,
            height=height,
            person_count=person_count,
            persons=persons,
            main_subject_area_ratio=round(
                main_subject_area_ratio,
                4,
            ),
            main_subject_center_score=round(
                subject_center_score,
                4,
            ),
            person_count_score=round(
                person_count_score,
                4,
            ),
            sharpness_score=round(
                sharpness_score,
                4,
            ),
            motion_score=round(
                motion_score,
                4,
            ),
            role_score=round(
                role_score,
                4,
            ),
            total_score=total_score,
        )

    # ========================================================
    # Synchronization helpers
    # ========================================================

    @staticmethod
    def _effective_offsets(
        synchronization: SynchronizationConfig,
    ) -> dict[str, float]:
        """Return a complete synchronization-offset mapping.

        If the GUI loaded incomplete/stale offsets but still has
        clap_times, rebuild the offsets from those measurements.
        """
        offsets = dict(getattr(synchronization, "offsets", {}) or {})
        clap_times = dict(getattr(synchronization, "clap_times", {}) or {})
        reference_camera_id = getattr(
            synchronization, "reference_camera_id", None
        )

        if clap_times and reference_camera_id:
            try:
                calculated = SynchronizationService().calculate_offsets(
                    clap_times,
                    reference_camera_id,
                )
                offsets.update(
                    dict(getattr(calculated, "offsets", {}) or {})
                )
            except Exception:
                # Keep the mapping already loaded by the GUI.
                pass

        return offsets

    def synchronization_status(
        self,
        cameras: list[CameraSource],
        synchronization: SynchronizationConfig,
    ) -> dict[str, Any]:
        """Return synchronization coverage for every camera."""
        offsets = self._effective_offsets(synchronization)
        return {
            "reference_camera_id": synchronization.reference_camera_id,
            "offsets": offsets,
            "camera_status": {
                camera.id: {
                    "has_offset": camera.id in offsets,
                    "offset": offsets.get(camera.id),
                    "file": camera.file,
                    "duration": camera.duration,
                }
                for camera in cameras
            },
        }

    # ========================================================
    # Analyze synchronized timeline
    # ========================================================

    def analyze_timeline(
        self,
        timeline_time: float,
        cameras: list[CameraSource],
        synchronization: SynchronizationConfig,
    ) -> list[FrameAnalysis]:
        """
        Analyze all available cameras at ONE synchronized
        timeline moment.

        This is the most important function for automatic
        multi-camera editing.
        """

        synchronization_service = (
            SynchronizationService()
        )

        # Rebuild offsets from clap_times when possible so a stale or
        # incomplete GUI mapping cannot silently reduce analysis to CAM001.
        effective_offsets = self._effective_offsets(
            synchronization
        )

        analyses: list[FrameAnalysis] = []

        for camera in cameras:

            # -----------------------------------------------
            # Check synchronization exists.
            # -----------------------------------------------

            if camera.id not in effective_offsets:
                continue

            # -----------------------------------------------
            # Convert timeline time -> source time.
            # -----------------------------------------------

            try:
                source_time = (
                    synchronization_service
                    .timeline_to_source_time(
                        timeline_time,
                        camera.id,
                        SynchronizationConfig(
                            reference_camera_id=synchronization.reference_camera_id,
                            clap_times=synchronization.clap_times,
                            offsets=effective_offsets,
                            approved=synchronization.approved,
                        ),
                    )
                )

            except Exception:
                # Camera is not available at this timeline position.
                #
                # Example:
                # timeline = 30
                # CAM002 offset = -57
                # source_time = -27
                #
                # CAM002 has not started yet.
                # Simply skip CAM002 and continue with the
                # other available cameras.
                continue

            # -----------------------------------------------
            # Check physical duration.
            # -----------------------------------------------

            if camera.duration > 0:

                if (
                    source_time < 0
                    or
                    source_time > camera.duration
                ):
                    continue

            # -----------------------------------------------
            # Analyze.
            # -----------------------------------------------

            try:
                analysis = self.analyze_camera(
                    camera,
                    source_time,
                )

            except Exception:
                # Do not let one broken camera stop analysis of
                # all other cameras.
                continue

            analyses.append(
                analysis
            )

        # Best camera first.
        analyses.sort(
            key=lambda item: (
                -item.total_score,
                item.camera_id,
            )
        )

        return analyses

    # ========================================================
    # Best camera
    # ========================================================

    def best_camera_at_time(
        self,
        timeline_time: float,
        cameras: list[CameraSource],
        synchronization: SynchronizationConfig,
    ) -> FrameAnalysis | None:
        """
        Return the highest-scoring camera at a timeline time.
        """

        analyses = self.analyze_timeline(
            timeline_time,
            cameras,
            synchronization,
        )

        if not analyses:
            return None

        return analyses[0]

    # ========================================================
    # Score dictionary
    # ========================================================

    def vision_scores_at_time(
        self,
        timeline_time: float,
        cameras: list[CameraSource],
        synchronization: SynchronizationConfig,
    ) -> dict[str, float]:
        """
        Return:

            {
                "CAM001": 72.4,
                "CAM002": 91.8,
                "CAM003": 78.5,
                "CAM004": 84.2
            }

        This is the format that camera_rules.py can consume.
        """

        analyses = self.analyze_timeline(
            timeline_time,
            cameras,
            synchronization,
        )

        return {
            analysis.camera_id:
            analysis.total_score
            for analysis in analyses
        }

    # ========================================================
    # Analyze a time range
    # ========================================================

    def analyze_range(
        self,
        timeline_start: float,
        timeline_end: float,
        cameras: list[CameraSource],
        synchronization: SynchronizationConfig,
        interval: float = 0.5,
    ) -> list[dict[str, Any]]:
        """
        Analyze a complete timeline range.

        Example:

            57 -> 70
            interval = 0.5

        Results:

            57.0
            57.5
            58.0
            58.5
            ...
            70.0

        This does NOT automatically cut cameras.

        It only produces the visual analysis data.

        The switch engine / EDL service will use these results
        later.
        """

        if timeline_end <= timeline_start:
            raise ValueError(
                "timeline_end must be greater than "
                "timeline_start."
            )

        if interval <= 0:
            raise ValueError(
                "interval must be greater than 0."
            )

        results: list[dict[str, Any]] = []

        current_time = timeline_start

        while current_time <= timeline_end + 0.000001:

            analyses = self.analyze_timeline(
                current_time,
                cameras,
                synchronization,
            )

            results.append(
                {
                    "timeline_time": round(
                        current_time,
                        3,
                    ),
                    "cameras": [
                        analysis.to_dict()
                        for analysis in analyses
                    ],
                }
            )

            current_time += interval

        return results

    # ========================================================
    # Reset motion state
    # ========================================================

    def reset_motion_state(self) -> None:
        """
        Clear previous frames.

        Call this before starting a new independent analysis.
        """

        self._previous_frames.clear()
        self._previous_times.clear()

    # ========================================================
    # Close / cleanup
    # ========================================================

    def close(self) -> None:
        """Release cached video captures and analysis state."""
        for capture in self._captures.values():
            try:
                capture.release()
            except Exception:
                pass

        self._captures.clear()
        self._model = None
        self.reset_motion_state()