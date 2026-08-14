# # from __future__ import annotations

# # import csv
# # import json
# # from dataclasses import replace
# # from pathlib import Path
# # from typing import Any

# # from .camera_rules import recommend_camera
# # from .models import CameraSource, EDLSegment, Overlay, ProgrammeSegment, Project, SynchronizationConfig, edl_from_dict, to_dict
# # from .project_service import atomic_write_json
# # from .synchronization import SynchronizationService

# # MATERIAL_FIELDS = {"timeline_start", "timeline_end", "selected_camera", "reason", "transition", "overlay"}


# # class EDLService:
# #     def generate(self, project: Project, cameras: list[CameraSource], programme: list[ProgrammeSegment], synchronization: SynchronizationConfig) -> list[EDLSegment]:
# #         sync = SynchronizationService()
# #         result: list[EDLSegment] = []
# #         previous: str | None = None
# #         for index, item in enumerate(programme):
# #             recommendation = recommend_camera(item, cameras, previous)
# #             overlay = Overlay("lower_third", project.lower_third) if index == 0 and project.lower_third else Overlay()
# #             result.append(EDLSegment(
# #                 item.id, item.start, item.end, recommendation.camera_id,
# #                 sync.timeline_to_source_time(item.start, recommendation.camera_id, synchronization),
# #                 sync.timeline_to_source_time(item.end, recommendation.camera_id, synchronization),
# #                 item.event_type, item.description, recommendation.reason,
# #                 "fade" if index == 0 else "cut", overlay,
# #             ))
# #             previous = recommendation.camera_id
# #         return result

# #     def update_segment(self, segment: EDLSegment, changes: dict[str, Any]) -> EDLSegment:
# #         unknown = set(changes) - set(segment.__dataclass_fields__)
# #         if unknown:
# #             raise ValueError(f"Unknown EDL fields: {', '.join(sorted(unknown))}")
# #         changed_materially = any(key in MATERIAL_FIELDS and getattr(segment, key) != value for key, value in changes.items())
# #         values = dict(changes)
# #         if isinstance(values.get("overlay"), dict):
# #             values["overlay"] = Overlay(**values["overlay"])
# #         if changed_materially:
# #             values["approved"] = False
# #             values["manually_modified"] = True
# #         return replace(segment, **values)

# #     def save(self, path: Path, project: Project, cameras: list[CameraSource], segments: list[EDLSegment], subtitles: list[Any] | None = None) -> None:
# #         atomic_write_json(path, {"schema_version": "1.0", "project": to_dict(project), "cameras": [to_dict(c) for c in cameras], "segments": [to_dict(s) for s in segments], "subtitles": [to_dict(s) for s in subtitles or []]})

# #     def load_segments(self, path: Path) -> list[EDLSegment]:
# #         return [edl_from_dict(item) for item in json.loads(path.read_text(encoding="utf-8"))["segments"]]

# #     def export_decisions(self, path: Path, segments: list[EDLSegment]) -> None:
# #         path.parent.mkdir(parents=True, exist_ok=True)
# #         with path.open("w", newline="", encoding="utf-8") as handle:
# #             writer = csv.writer(handle)
# #             writer.writerow(["segment_id", "camera", "event_type", "reason", "approved"])
# #             for item in segments:
# #                 writer.writerow([item.id, item.selected_camera, item.event_type, item.reason, item.approved])

# from __future__ import annotations

# import csv
# import json
# from dataclasses import replace
# from pathlib import Path
# from typing import Any

# from .camera_rules import (
#     camera_is_available,
#     get_available_cameras,
#     recommend_camera,
# )
# from .exceptions import EDLValidationError
# from .models import (
#     CameraSource,
#     EDLSegment,
#     Overlay,
#     ProgrammeSegment,
#     Project,
#     SynchronizationConfig,
#     edl_from_dict,
#     to_dict,
# )
# from .project_service import atomic_write_json
# from .synchronization import SynchronizationService
# from .vision_analyzer import VisionAnalyzer
# from .switch_engine import SwitchEngine


# # ============================================================
# # Configuration
# # ============================================================

# # True:
# #   Generate EDL using VisionAnalyzer + SwitchEngine.
# #
# # False:
# #   Use the older rule-based recommendation.
# #
# # For your project, keep this TRUE.
# USE_VISION_AUTO_EDIT = True


# # How frequently we LOOK at the video.
# #
# # IMPORTANT:
# #
# # This is NOT the camera cut interval.
# #
# # Example:
# #
# #   0.5 seconds
# #
# # means the AI checks the cameras every 0.5 seconds.
# #
# # It does NOT mean it cuts every 0.5 seconds.
# ANALYSIS_INTERVAL = 0.5


# # Minimum duration of one shot.
# MIN_SHOT_DURATION = 3.0


# # Candidate camera must be better by this many score points.
# SWITCH_MARGIN = 8.0


# # Candidate must remain better for this long.
# CONFIRMATION_DURATION = 1.5


# # Score smoothing.
# SMOOTHING_ALPHA = 0.35


# # ============================================================
# # Material fields
# # ============================================================

# MATERIAL_FIELDS = {
#     "timeline_start",
#     "timeline_end",
#     "selected_camera",
#     "source_start",
#     "source_end",
#     "reason",
#     "transition",
#     "overlay",
# }


# # ============================================================
# # EDL Service
# # ============================================================


# class EDLService:
#     """
#     Generate and manage EDL recommendations.

#     Automatic mode:

#         Programme Segment
#                 ↓
#         VisionAnalyzer
#                 ↓
#         Camera scores
#                 ↓
#         SwitchEngine
#                 ↓
#         KEEP / SWITCH
#                 ↓
#         ShotSegments
#                 ↓
#         EDL segments
#                 ↓
#         Human Review
#     """

#     def __init__(
#         self,
#         vision_analyzer: VisionAnalyzer | None = None,
#         switch_engine: SwitchEngine | None = None,
#     ) -> None:

#         self.vision_analyzer = (
#             vision_analyzer
#             if vision_analyzer is not None
#             else VisionAnalyzer()
#         )

#         self.switch_engine = (
#             switch_engine
#             if switch_engine is not None
#             else SwitchEngine(
#                 min_shot_duration=MIN_SHOT_DURATION,
#                 switch_margin=SWITCH_MARGIN,
#                 confirmation_duration=CONFIRMATION_DURATION,
#                 smoothing_alpha=SMOOTHING_ALPHA,
#                 analysis_interval=ANALYSIS_INTERVAL,
#             )
#         )

#     # ========================================================
#     # MAIN GENERATE FUNCTION
#     # ========================================================

#     def generate(
#         self,
#         project: Project,
#         cameras: list[CameraSource],
#         programme: list[ProgrammeSegment],
#         synchronization: SynchronizationConfig,
#     ) -> list[EDLSegment]:
#         """
#         Generate EDL recommendations.

#         In automatic mode:

#             1. Validate programme
#             2. Analyse synchronized cameras
#             3. Run SwitchEngine
#             4. Convert shot segments to EDL
#             5. Validate source ranges
#             6. Return EDL

#         The generated EDL is NOT automatically approved.
#         """

#         if not cameras:
#             raise EDLValidationError(
#                 "No cameras were imported."
#             )

#         if not programme:
#             return []

#         if synchronization is None:
#             raise EDLValidationError(
#                 "Synchronization is required before "
#                 "EDL generation."
#             )

#         result: list[EDLSegment] = []

#         # ----------------------------------------------------
#         # Process every programme segment.
#         # ----------------------------------------------------

#         for programme_segment in programme:

#             if (
#                 programme_segment.end
#                 <= programme_segment.start
#             ):
#                 raise EDLValidationError(
#                     f"Invalid programme segment "
#                     f"{programme_segment.id}: "
#                     f"end must be later than start."
#                 )

#             # ------------------------------------------------
#             # AUTOMATIC VISION MODE
#             # ------------------------------------------------

#             # if USE_VISION_AUTO_EDIT:

#             #     generated = (
#             #         self._generate_vision_edl(
#             #             project=project,
#             #             cameras=cameras,
#             #             programme_segment=programme_segment,
#             #             synchronization=synchronization,
#             #         )
#             #     )

#             # # ------------------------------------------------
#             # # LEGACY RULE-BASED MODE
#             # # ------------------------------------------------

#             # else:

#             #     generated = (
#             #         self._generate_rule_based_edl(
#             #             project=project,
#             #             cameras=cameras,
#             #             programme_segment=programme_segment,
#             #             synchronization=synchronization,
#             #             previous_camera_id=(
#             #                 result[-1].selected_camera
#             #                 if result
#             #                 else None
#             #             ),
#             #         )
#             #     )

#             if (
#                 USE_VISION_AUTO_EDIT
#                 and self._can_run_vision(cameras)
#             ):

#                 generated = (
#                     self._generate_vision_edl(
#                         project=project,
#                         cameras=cameras,
#                         programme_segment=programme_segment,
#                         synchronization=synchronization,
#                     )
#                 )

#             else:

#                 generated = (
#                     self._generate_rule_based_edl(
#                         project=project,
#                         cameras=cameras,
#                         programme_segment=programme_segment,
#                         synchronization=synchronization,
#                         previous_camera_id=(
#                             result[-1].selected_camera
#                             if result
#                             else None
#                         ),
#                     )
#                 )            

#             result.extend(generated)

#         # ----------------------------------------------------
#         # Merge adjacent same-camera EDL segments.
#         # ----------------------------------------------------

#         result = (
#             self._merge_adjacent_same_camera_segments(
#                 result
#             )
#         )

#         # ----------------------------------------------------
#         # Fix transitions.
#         # ----------------------------------------------------

#         result = self._apply_transitions(
#             result
#         )

#         return result

#     # ========================================================
#     # Check whether VisionAnalyzer can actually run
#     # ========================================================

#     @staticmethod
#     def _can_run_vision(
#         cameras: list[CameraSource],
#     ) -> bool:
#         """
#         Check whether the camera files required for Vision
#         analysis actually exist.

#         Vision analysis is used only when real video files are
#         available.

#         This allows unit tests and rule-only workflows to work
#         without requiring physical MP4 files.
#         """

#         if not cameras:
#             return False

#         for camera in cameras:

#             if not camera.file:
#                 return False

#             path = Path(
#                 camera.file
#             )

#             if not path.exists():
#                 return False

#         return True    

#     # ========================================================
#     # VISION AUTO EDL
#     # ========================================================

#     def _generate_vision_edl(
#         self,
#         project: Project,
#         cameras: list[CameraSource],
#         programme_segment: ProgrammeSegment,
#         synchronization: SynchronizationConfig,
#     ) -> list[EDLSegment]:
#         """
#         Generate EDL using actual video analysis.

#         Example:

#             Programme:

#                 00:57 -> 01:40

#             Vision analysis:

#                 C4 = best
#                 C4 = best
#                 C2 = best
#                 C2 = best
#                 C4 = best

#             SwitchEngine:

#                 57 -> 63 C4
#                 63 -> 71 C2
#                 71 -> 100 C4

#             EDL:

#                 57-63 C4
#                 63-71 C2
#                 71-100 C4
#         """

#         start = float(
#             programme_segment.start
#         )

#         end = float(
#             programme_segment.end
#         )

#         # ----------------------------------------------------
#         # First, make sure there is at least one usable camera.
#         # ----------------------------------------------------

#         available_at_start = (
#             get_available_cameras(
#                 cameras=cameras,
#                 timeline_start=start,
#                 timeline_end=min(
#                     start + 0.01,
#                     end,
#                 ),
#                 synchronization=synchronization,
#             )
#         )

#         if not available_at_start:

#             # It is possible that the programme starts before
#             # all cameras are available.
#             #
#             # Therefore find the first legal timeline point.
#             first_valid_time = (
#                 self._find_first_available_time(
#                     start,
#                     end,
#                     cameras,
#                     synchronization,
#                 )
#             )

#             if first_valid_time is None:
#                 raise EDLValidationError(
#                     f"No camera is available for "
#                     f"programme segment "
#                     f"{programme_segment.id}."
#                 )

#             start = first_valid_time

#         # ----------------------------------------------------
#         # Analyse the cameras.
#         # ----------------------------------------------------

#         self.vision_analyzer.reset_motion_state()

#         timeline_results = []

#         current_time = start

#         while current_time <= end + 0.000001:

#             analyses = (
#                 self.vision_analyzer
#                 .analyze_timeline(
#                     timeline_time=current_time,
#                     cameras=cameras,
#                     synchronization=synchronization,
#                 )
#             )

#             if analyses:
#                 timeline_results.append(
#                     (
#                         round(
#                             current_time,
#                             6,
#                         ),
#                         analyses,
#                     )
#                 )

#             current_time += (
#                 self.switch_engine.analysis_interval
#             )

#         # ----------------------------------------------------
#         # Make sure we actually got analysis results.
#         # ----------------------------------------------------

#         if not timeline_results:

#             raise EDLValidationError(
#                 f"Vision analysis returned no valid "
#                 f"camera frames for "
#                 f"{programme_segment.id}."
#             )

#         # ----------------------------------------------------
#         # Select initial camera.
#         #
#         # The highest-scoring valid camera at the first
#         # analysed timeline point becomes the starting camera.
#         # ----------------------------------------------------

#         first_time, first_analyses = (
#             timeline_results[0]
#         )

#         initial_camera = max(
#             first_analyses,
#             key=lambda item:
#             item.total_score,
#         )

#         initial_camera_id = (
#             initial_camera.camera_id
#         )

#         # ----------------------------------------------------
#         # Run SwitchEngine.
#         # ----------------------------------------------------

#         switch_result = (
#             self.switch_engine.analyze(
#                 timeline_results=timeline_results,
#                 timeline_start=start,
#                 timeline_end=end,
#                 initial_camera_id=initial_camera_id,
#             )
#         )

#         shot_segments = (
#             switch_result["segments"]
#         )

#         if not shot_segments:
#             raise EDLValidationError(
#                 f"SwitchEngine generated no shot "
#                 f"segments for {programme_segment.id}."
#             )

#         # ----------------------------------------------------
#         # Convert ShotSegments -> EDLSegments
#         # ----------------------------------------------------

#         edl_segments: list[EDLSegment] = []

#         for index, shot in enumerate(
#             shot_segments
#         ):

#             timeline_start = float(
#                 shot["start"]
#             )

#             timeline_end = float(
#                 shot["end"]
#             )

#             camera_id = (
#                 shot["camera_id"]
#             )

#             if (
#                 timeline_end
#                 <= timeline_start
#             ):
#                 continue

#             camera = self._find_camera(
#                 cameras,
#                 camera_id,
#             )

#             # ------------------------------------------------
#             # IMPORTANT:
#             #
#             # Make sure this camera can cover the COMPLETE
#             # shot.
#             # ------------------------------------------------

#             if not camera_is_available(
#                 camera=camera,
#                 timeline_start=timeline_start,
#                 timeline_end=timeline_end,
#                 synchronization=synchronization,
#             ):

#                 # This should normally never happen because
#                 # VisionAnalyzer only analyses valid cameras.
#                 #
#                 # But we keep this protection here to prevent
#                 # invalid EDL files.
#                 raise EDLValidationError(
#                     "SOURCE_RANGE_INVALID: "
#                     f"{camera_id} cannot cover "
#                     f"{timeline_start:.3f}s-"
#                     f"{timeline_end:.3f}s."
#                 )

#             # ------------------------------------------------
#             # Convert timeline -> source time.
#             # ------------------------------------------------

#             source_start = (
#                 self._timeline_to_source_time(
#                     timeline_start,
#                     camera_id,
#                     synchronization,
#                 )
#             )

#             source_end = (
#                 self._timeline_to_source_time(
#                     timeline_end,
#                     camera_id,
#                     synchronization,
#                 )
#             )

#             # ------------------------------------------------
#             # Validate source range.
#             # ------------------------------------------------

#             self._validate_source_range(
#                 camera=camera,
#                 source_start=source_start,
#                 source_end=source_end,
#                 segment_id=(
#                     f"{programme_segment.id}_"
#                     f"{index + 1:02d}"
#                 ),
#             )

#             # ------------------------------------------------
#             # Find the switch reason.
#             # ------------------------------------------------

#             reason = (
#                 self._build_vision_reason(
#                     shot=shot,
#                     camera=camera,
#                     timeline_results=timeline_results,
#                 )
#             )

#             # ------------------------------------------------
#             # Overlay
#             # ------------------------------------------------

#             if (
#                 index == 0
#                 and project.lower_third
#             ):
#                 overlay = Overlay(
#                     "lower_third",
#                     project.lower_third,
#                 )
#             else:
#                 overlay = Overlay()

#             # ------------------------------------------------
#             # Temporary transition.
#             #
#             # _apply_transitions() will fix first/next segment.
#             # ------------------------------------------------

#             transition = (
#                 "fade"
#                 if index == 0
#                 else "cut"
#             )

#             # ------------------------------------------------
#             # Create EDL segment.
#             # ------------------------------------------------

#             edl_segment = EDLSegment(
#                 id=(
#                     f"{programme_segment.id}_"
#                     f"{index + 1:02d}"
#                 ),
#                 timeline_start=timeline_start,
#                 timeline_end=timeline_end,
#                 selected_camera=camera_id,
#                 source_start=source_start,
#                 source_end=source_end,
#                 event_type=(
#                     programme_segment.event_type
#                 ),
#                 description=(
#                     programme_segment.description
#                 ),
#                 reason=reason,
#                 transition=transition,
#                 overlay=overlay,
#                 approved=False,
#                 manually_modified=False,
#             )

#             edl_segments.append(
#                 edl_segment
#             )

#         return edl_segments

#     # ========================================================
#     # RULE BASED FALLBACK
#     # ========================================================

#     def _generate_rule_based_edl(
#         self,
#         project: Project,
#         cameras: list[CameraSource],
#         programme_segment: ProgrammeSegment,
#         synchronization: SynchronizationConfig,
#         previous_camera_id: str | None,
#     ) -> list[EDLSegment]:
#         """
#         Legacy rule-based EDL generation.

#         This is kept as a fallback.

#         It does NOT analyse video frames.
#         """

#         ranges = (
#             self._split_by_camera_availability(
#                 programme_segment,
#                 cameras,
#                 synchronization,
#             )
#         )

#         result: list[EDLSegment] = []

#         for index, (
#             timeline_start,
#             timeline_end,
#         ) in enumerate(ranges):

#             available = (
#                 get_available_cameras(
#                     cameras=cameras,
#                     timeline_start=timeline_start,
#                     timeline_end=timeline_end,
#                     synchronization=synchronization,
#                 )
#             )

#             if not available:
#                 continue

#             segment = ProgrammeSegment(
#                 id=(
#                     f"{programme_segment.id}_"
#                     f"{index + 1:02d}"
#                 ),
#                 start=timeline_start,
#                 end=timeline_end,
#                 event_type=(
#                     programme_segment.event_type
#                 ),
#                 description=(
#                     programme_segment.description
#                 ),
#             )

#             recommendation = (
#                 recommend_camera(
#                     segment=segment,
#                     cameras=available,
#                     previous_camera_id=previous_camera_id,
#                     synchronization=synchronization,
#                 )
#             )

#             camera_id = (
#                 recommendation.camera_id
#             )

#             camera = self._find_camera(
#                 cameras,
#                 camera_id,
#             )

#             source_start = (
#                 self._timeline_to_source_time(
#                     timeline_start,
#                     camera_id,
#                     synchronization,
#                 )
#             )

#             source_end = (
#                 self._timeline_to_source_time(
#                     timeline_end,
#                     camera_id,
#                     synchronization,
#                 )
#             )

#             self._validate_source_range(
#                 camera,
#                 source_start,
#                 source_end,
#                 segment.id,
#             )

#             overlay = (
#                 Overlay(
#                     "lower_third",
#                     project.lower_third,
#                 )
#                 if index == 0
#                 and project.lower_third
#                 else Overlay()
#             )

#             result.append(
#                 EDLSegment(
#                     id=segment.id,
#                     timeline_start=timeline_start,
#                     timeline_end=timeline_end,
#                     selected_camera=camera_id,
#                     source_start=source_start,
#                     source_end=source_end,
#                     event_type=segment.event_type,
#                     description=segment.description,
#                     reason=recommendation.reason,
#                     transition=(
#                         "fade"
#                         if index == 0
#                         else "cut"
#                     ),
#                     overlay=overlay,
#                     approved=False,
#                     manually_modified=False,
#                 )
#             )

#             previous_camera_id = camera_id

#         return result

#     # ========================================================
#     # Timeline -> source
#     # ========================================================

#     @staticmethod
#     def _timeline_to_source_time(
#         timeline_time: float,
#         camera_id: str,
#         synchronization: SynchronizationConfig,
#     ) -> float:
#         """
#         Convert synchronized timeline time to source time.
#         """

#         if camera_id not in (
#             synchronization.offsets
#         ):
#             raise EDLValidationError(
#                 f"No synchronization offset "
#                 f"for camera {camera_id}."
#             )

#         return round(
#             timeline_time
#             + synchronization.offsets[
#                 camera_id
#             ],
#             6,
#         )

#     # ========================================================
#     # Find first valid time
#     # ========================================================

#     def _find_first_available_time(
#         self,
#         start: float,
#         end: float,
#         cameras: list[CameraSource],
#         synchronization: SynchronizationConfig,
#     ) -> float | None:
#         """
#         Find the earliest timeline point where at least one
#         camera is available.
#         """

#         boundaries = []

#         for camera in cameras:

#             if camera.id not in (
#                 synchronization.offsets
#             ):
#                 continue

#             offset = (
#                 synchronization.offsets[
#                     camera.id
#                 ]
#             )

#             camera_start = -offset

#             if (
#                 start
#                 <= camera_start
#                 <= end
#             ):
#                 boundaries.append(
#                     camera_start
#                 )

#         boundaries.append(start)

#         for candidate in sorted(
#             boundaries
#         ):

#             available = (
#                 get_available_cameras(
#                     cameras=cameras,
#                     timeline_start=candidate,
#                     timeline_end=min(
#                         candidate + 0.01,
#                         end,
#                     ),
#                     synchronization=synchronization,
#                 )
#             )

#             if available:
#                 return candidate

#         return None

#     # ========================================================
#     # Split by availability
#     # ========================================================

#     def _split_by_camera_availability(
#         self,
#         programme_segment: ProgrammeSegment,
#         cameras: list[CameraSource],
#         synchronization: SynchronizationConfig,
#     ) -> list[tuple[float, float]]:
#         """
#         Split programme segment at camera availability boundaries.

#         IMPORTANT:

#         These are technical boundaries only.

#         They do NOT mean a visual camera cut is required.
#         """

#         start = float(
#             programme_segment.start
#         )

#         end = float(
#             programme_segment.end
#         )

#         boundaries: set[float] = {
#             start,
#             end,
#         }

#         for camera in cameras:

#             if camera.id not in (
#                 synchronization.offsets
#             ):
#                 continue

#             offset = (
#                 synchronization.offsets[
#                     camera.id
#                 ]
#             )

#             # source = timeline + offset
#             #
#             # source = 0
#             #
#             # timeline = -offset

#             camera_start = -offset

#             if (
#                 start
#                 < camera_start
#                 < end
#             ):
#                 boundaries.add(
#                     round(
#                         camera_start,
#                         6,
#                     )
#                 )

#             if camera.duration > 0:

#                 camera_end = (
#                     camera.duration
#                     - offset
#                 )

#                 if (
#                     start
#                     < camera_end
#                     < end
#                 ):
#                     boundaries.add(
#                         round(
#                             camera_end,
#                             6,
#                         )
#                     )

#         sorted_boundaries = sorted(
#             boundaries
#         )

#         ranges = []

#         for index in range(
#             len(sorted_boundaries) - 1
#         ):

#             range_start = (
#                 sorted_boundaries[index]
#             )

#             range_end = (
#                 sorted_boundaries[index + 1]
#             )

#             if (
#                 range_end
#                 > range_start
#             ):
#                 ranges.append(
#                     (
#                         range_start,
#                         range_end,
#                     )
#                 )

#         return ranges

#     # ========================================================
#     # Find camera
#     # ========================================================

#     @staticmethod
#     def _find_camera(
#         cameras: list[CameraSource],
#         camera_id: str,
#     ) -> CameraSource:
#         """
#         Find camera by ID.
#         """

#         for camera in cameras:

#             if camera.id == camera_id:
#                 return camera

#         raise EDLValidationError(
#             f"Camera {camera_id} does not exist."
#         )

#     # ========================================================
#     # Validate source range
#     # ========================================================

#     @staticmethod
#     def _validate_source_range(
#         camera: CameraSource,
#         source_start: float,
#         source_end: float,
#         segment_id: str,
#         tolerance: float = 0.05,
#     ) -> None:
#         """
#         Validate EDL source range against the camera recording.
#         """

#         if source_start < -tolerance:

#             raise EDLValidationError(
#                 "SOURCE_RANGE_INVALID: "
#                 f"Segment {segment_id} starts at "
#                 f"{source_start:.3f}s in "
#                 f"{camera.id}."
#             )

#         if source_end <= source_start:

#             raise EDLValidationError(
#                 "SOURCE_RANGE_INVALID: "
#                 f"Segment {segment_id} has an invalid "
#                 "source range."
#             )

#         if camera.duration > 0:

#             if (
#                 source_end
#                 > camera.duration
#                 + tolerance
#             ):

#                 raise EDLValidationError(
#                     "SOURCE_RANGE_INVALID: "
#                     f"Segment {segment_id} ends at "
#                     f"{source_end:.3f}s, but "
#                     f"{camera.id} duration is "
#                     f"{camera.duration:.3f}s."
#                 )

#     # ========================================================
#     # Build Vision Reason
#     # ========================================================

#     def _build_vision_reason(
#         self,
#         shot: dict[str, Any],
#         camera: CameraSource,
#         timeline_results: list[
#             tuple[
#                 float,
#                 list[Any],
#             ]
#         ],
#     ) -> str:
#         """
#         Create an explainable recommendation reason.

#         Example:

#             CAM002 selected because visual analysis found
#             a stronger main-subject composition and the camera
#             remained the highest-scoring valid camera.
#         """

#         start = float(
#             shot["start"]
#         )

#         end = float(
#             shot["end"]
#         )

#         # Find analyses inside this shot.
#         relevant = []

#         for timeline_time, analyses in (
#             timeline_results
#         ):

#             if (
#                 start
#                 <= timeline_time
#                 <= end
#             ):

#                 for analysis in analyses:

#                     if (
#                         analysis.camera_id
#                         == camera.id
#                     ):
#                         relevant.append(
#                             analysis
#                         )

#         if not relevant:

#             return (
#                 f"{camera.name} was selected by "
#                 "automatic vision analysis."
#             )

#         average_score = (
#             sum(
#                 item.total_score
#                 for item in relevant
#             )
#             / len(relevant)
#         )

#         average_subject_size = (
#             sum(
#                 item.main_subject_area_ratio
#                 for item in relevant
#             )
#             / len(relevant)
#         )

#         average_sharpness = (
#             sum(
#                 item.sharpness_score
#                 for item in relevant
#             )
#             / len(relevant)
#         )

#         average_motion = (
#             sum(
#                 item.motion_score
#                 for item in relevant
#             )
#             / len(relevant)
#         )

#         return (
#             f"{camera.name} selected by automatic "
#             f"vision analysis. "
#             f"Average vision score: "
#             f"{average_score:.1f}/100; "
#             f"main subject area: "
#             f"{average_subject_size:.1%}; "
#             f"sharpness: "
#             f"{average_sharpness:.2f}; "
#             f"motion: "
#             f"{average_motion:.2f}."
#         )

#     # ========================================================
#     # Merge adjacent same-camera segments
#     # ========================================================

#     @staticmethod
#     def _merge_adjacent_same_camera_segments(
#         segments: list[EDLSegment],
#     ) -> list[EDLSegment]:
#         """
#         Merge adjacent EDL segments using the same camera.

#         This prevents technical boundaries from becoming
#         unnecessary visual cuts.
#         """

#         if not segments:
#             return []

#         merged = [
#             segments[0]
#         ]

#         for current in segments[1:]:

#             previous = merged[-1]

#             same_camera = (
#                 previous.selected_camera
#                 == current.selected_camera
#             )

#             adjacent = (
#                 abs(
#                     previous.timeline_end
#                     - current.timeline_start
#                 )
#                 < 0.000001
#             )

#             same_event = (
#                 previous.event_type
#                 == current.event_type
#             )

#             not_manual = (
#                 not previous.manually_modified
#                 and not current.manually_modified
#             )

#             if (
#                 same_camera
#                 and adjacent
#                 and same_event
#                 and not_manual
#             ):

#                 merged[-1] = EDLSegment(
#                     id=previous.id,
#                     timeline_start=(
#                         previous.timeline_start
#                     ),
#                     timeline_end=(
#                         current.timeline_end
#                     ),
#                     selected_camera=(
#                         previous.selected_camera
#                     ),
#                     source_start=(
#                         previous.source_start
#                     ),
#                     source_end=(
#                         current.source_end
#                     ),
#                     event_type=(
#                         previous.event_type
#                     ),
#                     description=(
#                         previous.description
#                     ),
#                     reason=(
#                         previous.reason
#                     ),
#                     transition=(
#                         previous.transition
#                     ),
#                     overlay=(
#                         previous.overlay
#                     ),
#                     approved=False,
#                     manually_modified=False,
#                 )

#             else:
#                 merged.append(
#                     current
#                 )

#         return merged

#     # ========================================================
#     # Apply transitions
#     # ========================================================

#     @staticmethod
#     def _apply_transitions(
#         segments: list[EDLSegment],
#     ) -> list[EDLSegment]:
#         """
#         First shot = fade.
#         Camera switches = cut.

#         This can later be expanded to support configurable
#         transitions.
#         """

#         if not segments:
#             return []

#         result = []

#         for index, segment in enumerate(
#             segments
#         ):

#             transition = (
#                 "fade"
#                 if index == 0
#                 else "cut"
#             )

#             result.append(
#                 replace(
#                     segment,
#                     transition=transition,
#                 )
#             )

#         return result

#     # ========================================================
#     # Human Review: Update segment
#     # ========================================================

#     def update_segment(
#         self,
#         segment: EDLSegment,
#         changes: dict[str, Any],
#     ) -> EDLSegment:
#         """
#         Update an EDL segment during Human Review.

#         If the user changes Camera/time/transition/etc.,
#         approval is reset and manually_modified becomes True.
#         """

#         valid_fields = set(
#             segment.__dataclass_fields__
#         )

#         unknown = (
#             set(changes)
#             - valid_fields
#         )

#         if unknown:

#             raise ValueError(
#                 "Unknown EDL fields: "
#                 + ", ".join(
#                     sorted(unknown)
#                 )
#             )

#         changed_materially = any(
#             key in MATERIAL_FIELDS
#             and getattr(
#                 segment,
#                 key,
#             ) != value
#             for key, value in changes.items()
#         )

#         values = dict(
#             changes
#         )

#         # ----------------------------------------------------
#         # Convert overlay dict to Overlay object.
#         # ----------------------------------------------------

#         if isinstance(
#             values.get("overlay"),
#             dict,
#         ):

#             values["overlay"] = Overlay(
#                 **values["overlay"]
#             )

#         # ----------------------------------------------------
#         # Human modification resets approval.
#         # ----------------------------------------------------

#         if changed_materially:

#             values["approved"] = False

#             values[
#                 "manually_modified"
#             ] = True

#         return replace(
#             segment,
#             **values,
#         )

#     # ========================================================
#     # Save
#     # ========================================================

#     def save(
#         self,
#         path: Path,
#         project: Project,
#         cameras: list[CameraSource],
#         segments: list[EDLSegment],
#         subtitles: list[Any] | None = None,
#     ) -> None:
#         """
#         Save project and EDL data.
#         """

#         atomic_write_json(
#             path,
#             {
#                 "schema_version": "1.0",

#                 "project": to_dict(
#                     project
#                 ),

#                 "cameras": [
#                     to_dict(camera)
#                     for camera in cameras
#                 ],

#                 "segments": [
#                     to_dict(segment)
#                     for segment in segments
#                 ],

#                 "subtitles": [
#                     to_dict(item)
#                     for item in (
#                         subtitles or []
#                     )
#                 ],
#             },
#         )

#     # ========================================================
#     # Load
#     # ========================================================

#     def load_segments(
#         self,
#         path: Path,
#     ) -> list[EDLSegment]:
#         """
#         Load EDL segments from JSON.
#         """

#         data = json.loads(
#             path.read_text(
#                 encoding="utf-8"
#             )
#         )

#         return [
#             edl_from_dict(item)
#             for item in data[
#                 "segments"
#             ]
#         ]

#     # ========================================================
#     # Export CSV
#     # ========================================================

#     def export_decisions(
#         self,
#         path: Path,
#         segments: list[EDLSegment],
#     ) -> None:
#         """
#         Export EDL decisions as CSV.
#         """

#         path.parent.mkdir(
#             parents=True,
#             exist_ok=True,
#         )

#         with path.open(
#             "w",
#             newline="",
#             encoding="utf-8",
#         ) as handle:

#             writer = csv.writer(
#                 handle
#             )

#             writer.writerow(
#                 [
#                     "segment_id",
#                     "timeline_start",
#                     "timeline_end",
#                     "camera",
#                     "source_start",
#                     "source_end",
#                     "event_type",
#                     "transition",
#                     "reason",
#                     "approved",
#                 ]
#             )

#             for segment in segments:

#                 writer.writerow(
#                     [
#                         segment.id,
#                         f"{segment.timeline_start:.3f}",
#                         f"{segment.timeline_end:.3f}",
#                         segment.selected_camera,
#                         f"{segment.source_start:.3f}",
#                         f"{segment.source_end:.3f}",
#                         segment.event_type,
#                         segment.transition,
#                         segment.reason,
#                         segment.approved,
#                     ]
#                 )

#     # ========================================================
#     # Diagnostic
#     # ========================================================

#     def diagnose(
#         self,
#         cameras: list[CameraSource],
#         programme: list[ProgrammeSegment],
#         synchronization: SynchronizationConfig,
#     ) -> list[dict[str, Any]]:
#         """
#         Diagnose camera availability before generating EDL.
#         """

#         diagnostics = []

#         for item in programme:

#             available = (
#                 get_available_cameras(
#                     cameras=cameras,
#                     timeline_start=item.start,
#                     timeline_end=item.end,
#                     synchronization=synchronization,
#                 )
#             )

#             camera_status = {}

#             for camera in cameras:

#                 camera_status[
#                     camera.id
#                 ] = camera_is_available(
#                     camera,
#                     item.start,
#                     item.end,
#                     synchronization,
#                 )

#             diagnostics.append(
#                 {
#                     "segment_id": item.id,
#                     "timeline_start": item.start,
#                     "timeline_end": item.end,
#                     "available_cameras": [
#                         camera.id
#                         for camera in available
#                     ],
#                     "camera_status": camera_status,
#                 }
#             )

#         return diagnostics

#     # ========================================================
#     # Cleanup
#     # ========================================================

#     def close(self) -> None:
#         """
#         Release VisionAnalyzer resources.
#         """

#         if self.vision_analyzer:
#             self.vision_analyzer.close()

from __future__ import annotations

import csv
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from .camera_rules import (
    camera_is_available,
    get_available_cameras,
    recommend_camera,
)
from .exceptions import EDLValidationError
from .models import (
    CameraSource,
    EDLSegment,
    Overlay,
    ProgrammeSegment,
    Project,
    SynchronizationConfig,
    edl_from_dict,
    to_dict,
)
from .project_service import atomic_write_json
from .vision_analyzer import VisionAnalyzer
from .switch_engine import SwitchEngine


# ============================================================
# Configuration
# ============================================================

# True:
#   Use VisionAnalyzer + SwitchEngine.
#
# False:
#   Use the old rule-based camera recommendation.
USE_VISION_AUTO_EDIT = True


# How frequently the AI analyses the video.
#
# IMPORTANT:
# This is NOT the camera cut interval.
#
# Example:
#
#     0.5
#
# means:
#
#     analyse every 0.5 seconds
#
# SwitchEngine decides whether an actual camera switch
# should happen.
ANALYSIS_INTERVAL = 0.5


# Minimum duration of a camera shot.
MIN_SHOT_DURATION = 3.0


# Candidate camera must beat the current camera
# by at least this many points.
SWITCH_MARGIN = 5.0


# Candidate must remain better for this amount of time.
CONFIRMATION_DURATION = 1.0


# Score smoothing.
#
# 0.7 means the newest analysis has stronger influence.
SMOOTHING_ALPHA = 0.7


# ============================================================
# Material EDL fields
# ============================================================

MATERIAL_FIELDS = {
    "timeline_start",
    "timeline_end",
    "selected_camera",
    "source_start",
    "source_end",
    "reason",
    "transition",
    "overlay",
}


# ============================================================
# EDL Service
# ============================================================

class EDLService:
    """
    Main service for generating the edit decision list.

    Automatic workflow:

        Programme Segment
                ↓
        Synchronization
                ↓
        VisionAnalyzer
                ↓
        Camera Scores
                ↓
        SwitchEngine
                ↓
        Camera Decisions
                ↓
        Shot Segments
                ↓
        EDL Segments
                ↓
        Human Review
    """

    def __init__(
        self,
        vision_analyzer: VisionAnalyzer | None = None,
        switch_engine: SwitchEngine | None = None,
    ) -> None:

        self.vision_analyzer = (
            vision_analyzer
            if vision_analyzer is not None
            else VisionAnalyzer()
        )

        self.switch_engine = (
            switch_engine
            if switch_engine is not None
            else SwitchEngine(
                min_shot_duration=MIN_SHOT_DURATION,
                switch_margin=SWITCH_MARGIN,
                confirmation_duration=CONFIRMATION_DURATION,
                smoothing_alpha=SMOOTHING_ALPHA,
                analysis_interval=ANALYSIS_INTERVAL,
                main_camera_id="CAM001",
            )
        )

    # ========================================================
    # MAIN GENERATE
    # ========================================================

    def generate(
        self,
        project: Project,
        cameras: list[CameraSource],
        programme: list[ProgrammeSegment],
        synchronization: SynchronizationConfig,
    ) -> list[EDLSegment]:

        if not cameras:
            raise EDLValidationError(
                "No cameras were imported."
            )

        if not programme:
            return []

        if synchronization is None:
            raise EDLValidationError(
                "Synchronization is required before EDL generation."
            )

        result: list[EDLSegment] = []

        for programme_segment in programme:

            if programme_segment.end <= programme_segment.start:
                raise EDLValidationError(
                    f"Invalid programme segment "
                    f"{programme_segment.id}: "
                    f"end must be later than start."
                )

            # ------------------------------------------------
            # Vision Auto Edit
            # ------------------------------------------------

            if (
                USE_VISION_AUTO_EDIT
                and self._can_run_vision(cameras)
            ):
                generated = self._generate_vision_edl(
                    project=project,
                    cameras=cameras,
                    programme_segment=programme_segment,
                    synchronization=synchronization,
                )

            # ------------------------------------------------
            # Rule-based fallback
            # ------------------------------------------------

            else:
                generated = self._generate_rule_based_edl(
                    project=project,
                    cameras=cameras,
                    programme_segment=programme_segment,
                    synchronization=synchronization,
                    previous_camera_id=(
                        result[-1].selected_camera
                        if result
                        else None
                    ),
                )

            result.extend(generated)

        # ----------------------------------------------------
        # Merge adjacent same-camera segments.
        #
        # IMPORTANT:
        #
        # This does NOT remove actual camera switches.
        # It only merges:
        #
        # CAM001
        # CAM001
        #
        # into:
        #
        # CAM001
        # ----------------------------------------------------

        result = self._merge_adjacent_same_camera_segments(
            result
        )

        # ----------------------------------------------------
        # Apply transitions.
        # ----------------------------------------------------

        result = self._apply_transitions(
            result
        )

        return result

    # ========================================================
    # Can Vision Run?
    # ========================================================

    @staticmethod
    def _can_run_vision(
        cameras: list[CameraSource],
    ) -> bool:

        if not cameras:
            return False

        for camera in cameras:

            if not camera.file:
                return False

            path = Path(
                camera.file
            )

            if not path.exists():
                return False

        return True

    # ========================================================
    # VISION AUTO EDL
    # ========================================================

    def _generate_vision_edl(
        self,
        project: Project,
        cameras: list[CameraSource],
        programme_segment: ProgrammeSegment,
        synchronization: SynchronizationConfig,
    ) -> list[EDLSegment]:

        start = float(
            programme_segment.start
        )

        end = float(
            programme_segment.end
        )

        # ----------------------------------------------------
        # Check if at least one camera is available.
        # ----------------------------------------------------

        available_at_start = (
            get_available_cameras(
                cameras=cameras,
                timeline_start=start,
                timeline_end=min(
                    start + 0.01,
                    end,
                ),
                synchronization=synchronization,
            )
        )

        if not available_at_start:

            first_valid_time = (
                self._find_first_available_time(
                    start=start,
                    end=end,
                    cameras=cameras,
                    synchronization=synchronization,
                )
            )

            if first_valid_time is None:
                raise EDLValidationError(
                    f"No camera is available for "
                    f"programme segment "
                    f"{programme_segment.id}."
                )

            start = first_valid_time

        # ----------------------------------------------------
        # Reset VisionAnalyzer state.
        # ----------------------------------------------------

        self.vision_analyzer.reset_motion_state()

        timeline_results: list[
            tuple[float, list[Any]]
        ] = []

        current_time = start

        # ----------------------------------------------------
        # Analyse timeline.
        # ----------------------------------------------------

        while current_time <= end + 0.000001:

            analyses = (
                self.vision_analyzer.analyze_timeline(
                    timeline_time=current_time,
                    cameras=cameras,
                    synchronization=synchronization,
                )
            )

            if analyses:

                timeline_results.append(
                    (
                        round(
                            current_time,
                            6,
                        ),
                        analyses,
                    )
                )

            current_time += (
                self.switch_engine.analysis_interval
            )

        # ----------------------------------------------------
        # Make sure analysis succeeded.
        # ----------------------------------------------------

        if not timeline_results:

            raise EDLValidationError(
                f"Vision analysis returned no valid "
                f"camera frames for "
                f"{programme_segment.id}."
            )

        # ----------------------------------------------------
        # IMPORTANT DIAGNOSTIC
        #
        # Show exactly what VisionAnalyzer gave
        # to SwitchEngine.
        # ----------------------------------------------------

        print()
        print("=" * 70)
        print("VISION ANALYSIS RESULT")
        print("=" * 70)

        for timeline_time, analyses in timeline_results:

            camera_scores = []

            for analysis in analyses:

                camera_scores.append(
                    (
                        analysis.camera_id,
                        round(
                            analysis.total_score,
                            2,
                        ),
                    )
                )

            print(
                f"{timeline_time:8.2f}s -> "
                f"{camera_scores}"
            )

        print("=" * 70)

        # ----------------------------------------------------
        # Initial camera.
        #
        # CAM001 is the preferred MAIN camera.
        #
        # We deliberately do NOT simply choose the highest
        # score here because the project requirement is:
        #
        # CAM001 = default main camera.
        #
        # SwitchEngine will move away from CAM001 only when
        # another camera is clearly better.
        # ----------------------------------------------------

        initial_camera_id = "CAM001"

        # If CAM001 is not available at the first analysed
        # point, allow SwitchEngine to start with a valid
        # camera.
        first_time, first_analyses = (
            timeline_results[0]
        )

        first_camera_ids = {
            analysis.camera_id
            for analysis in first_analyses
        }

        if initial_camera_id not in first_camera_ids:

            initial_camera = max(
                first_analyses,
                key=lambda item: item.total_score,
            )

            initial_camera_id = (
                initial_camera.camera_id
            )

        print(
            f"INITIAL CAMERA: {initial_camera_id}"
        )

        print("=" * 70)
        print()

        # ----------------------------------------------------
        # Run SwitchEngine.
        # ----------------------------------------------------

        switch_result = (
            self.switch_engine.analyze(
                timeline_results=timeline_results,
                timeline_start=start,
                timeline_end=end,
                initial_camera_id=initial_camera_id,
            )
        )

        shot_segments = (
            switch_result.get(
                "segments",
                [],
            )
        )

        # ----------------------------------------------------
        # IMPORTANT DIAGNOSTIC
        #
        # Show what SwitchEngine actually produced.
        # ----------------------------------------------------

        print()
        print("=" * 70)
        print("SWITCH ENGINE RESULT")
        print("=" * 70)

        switches = (
            switch_result.get(
                "switches",
                [],
            )
        )

        print(
            "Switches:"
        )

        for switch in switches:
            print(
                " ",
                switch,
            )

        print(
            "Shot Segments:"
        )

        for shot in shot_segments:

            print(
                f"  "
                f"{float(shot['start']):.3f}s"
                f" -> "
                f"{float(shot['end']):.3f}s"
                f" : "
                f"{shot['camera_id']}"
            )

        print("=" * 70)
        print()

        if not shot_segments:

            raise EDLValidationError(
                f"SwitchEngine generated no shot "
                f"segments for "
                f"{programme_segment.id}."
            )

        # ----------------------------------------------------
        # Convert ShotSegments -> EDL segments.
        # ----------------------------------------------------

        edl_segments: list[EDLSegment] = []

        for index, shot in enumerate(
            shot_segments
        ):

            timeline_start = float(
                shot["start"]
            )

            timeline_end = float(
                shot["end"]
            )

            camera_id = (
                shot["camera_id"]
            )

            if timeline_end <= timeline_start:
                continue

            camera = self._find_camera(
                cameras,
                camera_id,
            )

            # ------------------------------------------------
            # Camera must cover complete shot.
            # ------------------------------------------------

            if not camera_is_available(
                camera=camera,
                timeline_start=timeline_start,
                timeline_end=timeline_end,
                synchronization=synchronization,
            ):

                raise EDLValidationError(
                    "SOURCE_RANGE_INVALID: "
                    f"{camera_id} cannot cover "
                    f"{timeline_start:.3f}s-"
                    f"{timeline_end:.3f}s."
                )

            # ------------------------------------------------
            # Timeline -> source time.
            # ------------------------------------------------

            source_start = (
                self._timeline_to_source_time(
                    timeline_time=timeline_start,
                    camera_id=camera_id,
                    synchronization=synchronization,
                )
            )

            source_end = (
                self._timeline_to_source_time(
                    timeline_time=timeline_end,
                    camera_id=camera_id,
                    synchronization=synchronization,
                )
            )

            # ------------------------------------------------
            # Validate source range.
            # ------------------------------------------------

            segment_id = (
                f"{programme_segment.id}_"
                f"{index + 1:02d}"
            )

            self._validate_source_range(
                camera=camera,
                source_start=source_start,
                source_end=source_end,
                segment_id=segment_id,
            )

            # ------------------------------------------------
            # Explainable reason.
            # ------------------------------------------------

            reason = (
                self._build_vision_reason(
                    shot=shot,
                    camera=camera,
                    timeline_results=timeline_results,
                )
            )

            # ------------------------------------------------
            # Overlay.
            # ------------------------------------------------

            if (
                index == 0
                and project.lower_third
            ):

                overlay = Overlay(
                    "lower_third",
                    project.lower_third,
                )

            else:

                overlay = Overlay()

            # ------------------------------------------------
            # Transition.
            # ------------------------------------------------

            transition = (
                "fade"
                if index == 0
                else "cut"
            )

            # ------------------------------------------------
            # Create EDL segment.
            # ------------------------------------------------

            edl_segment = EDLSegment(
                id=segment_id,
                timeline_start=timeline_start,
                timeline_end=timeline_end,
                selected_camera=camera_id,
                source_start=source_start,
                source_end=source_end,
                event_type=(
                    programme_segment.event_type
                ),
                description=(
                    programme_segment.description
                ),
                reason=reason,
                transition=transition,
                overlay=overlay,
                approved=False,
                manually_modified=False,
            )

            edl_segments.append(
                edl_segment
            )

        return edl_segments

    # ========================================================
    # RULE BASED FALLBACK
    # ========================================================

    def _generate_rule_based_edl(
        self,
        project: Project,
        cameras: list[CameraSource],
        programme_segment: ProgrammeSegment,
        synchronization: SynchronizationConfig,
        previous_camera_id: str | None,
    ) -> list[EDLSegment]:

        ranges = (
            self._split_by_camera_availability(
                programme_segment=programme_segment,
                cameras=cameras,
                synchronization=synchronization,
            )
        )

        result: list[EDLSegment] = []

        for index, (
            timeline_start,
            timeline_end,
        ) in enumerate(ranges):

            available = (
                get_available_cameras(
                    cameras=cameras,
                    timeline_start=timeline_start,
                    timeline_end=timeline_end,
                    synchronization=synchronization,
                )
            )

            if not available:
                continue

            segment = ProgrammeSegment(
                id=(
                    f"{programme_segment.id}_"
                    f"{index + 1:02d}"
                ),
                start=timeline_start,
                end=timeline_end,
                event_type=(
                    programme_segment.event_type
                ),
                description=(
                    programme_segment.description
                ),
            )

            recommendation = (
                recommend_camera(
                    segment=segment,
                    cameras=available,
                    previous_camera_id=previous_camera_id,
                    synchronization=synchronization,
                )
            )

            camera_id = (
                recommendation.camera_id
            )

            camera = self._find_camera(
                cameras,
                camera_id,
            )

            source_start = (
                self._timeline_to_source_time(
                    timeline_time=timeline_start,
                    camera_id=camera_id,
                    synchronization=synchronization,
                )
            )

            source_end = (
                self._timeline_to_source_time(
                    timeline_time=timeline_end,
                    camera_id=camera_id,
                    synchronization=synchronization,
                )
            )

            self._validate_source_range(
                camera=camera,
                source_start=source_start,
                source_end=source_end,
                segment_id=segment.id,
            )

            if (
                index == 0
                and project.lower_third
            ):

                overlay = Overlay(
                    "lower_third",
                    project.lower_third,
                )

            else:

                overlay = Overlay()

            result.append(
                EDLSegment(
                    id=segment.id,
                    timeline_start=timeline_start,
                    timeline_end=timeline_end,
                    selected_camera=camera_id,
                    source_start=source_start,
                    source_end=source_end,
                    event_type=segment.event_type,
                    description=segment.description,
                    reason=recommendation.reason,
                    transition=(
                        "fade"
                        if index == 0
                        else "cut"
                    ),
                    overlay=overlay,
                    approved=False,
                    manually_modified=False,
                )
            )

            previous_camera_id = camera_id

        return result

    # ========================================================
    # Timeline -> Source
    # ========================================================

    @staticmethod
    def _timeline_to_source_time(
        timeline_time: float,
        camera_id: str,
        synchronization: SynchronizationConfig,
    ) -> float:

        if camera_id not in synchronization.offsets:

            raise EDLValidationError(
                f"No synchronization offset "
                f"for camera {camera_id}."
            )

        value = (
            timeline_time
            + synchronization.offsets[
                camera_id
            ]
        )

        if value < 0:

            raise EDLValidationError(
                f"Timeline time {timeline_time:.3f}s "
                f"maps before the beginning of "
                f"camera {camera_id}."
            )

        return round(
            value,
            6,
        )

    # ========================================================
    # Find first available time
    # ========================================================

    def _find_first_available_time(
        self,
        start: float,
        end: float,
        cameras: list[CameraSource],
        synchronization: SynchronizationConfig,
    ) -> float | None:

        boundaries: list[float] = []

        for camera in cameras:

            if camera.id not in synchronization.offsets:
                continue

            offset = (
                synchronization.offsets[
                    camera.id
                ]
            )

            camera_start = -offset

            if (
                start
                <= camera_start
                <= end
            ):

                boundaries.append(
                    camera_start
                )

        boundaries.append(
            start
        )

        for candidate in sorted(
            boundaries
        ):

            available = (
                get_available_cameras(
                    cameras=cameras,
                    timeline_start=candidate,
                    timeline_end=min(
                        candidate + 0.01,
                        end,
                    ),
                    synchronization=synchronization,
                )
            )

            if available:
                return candidate

        return None

    # ========================================================
    # Split by Camera Availability
    # ========================================================

    def _split_by_camera_availability(
        self,
        programme_segment: ProgrammeSegment,
        cameras: list[CameraSource],
        synchronization: SynchronizationConfig,
    ) -> list[tuple[float, float]]:

        start = float(
            programme_segment.start
        )

        end = float(
            programme_segment.end
        )

        boundaries: set[float] = {
            start,
            end,
        }

        for camera in cameras:

            if camera.id not in synchronization.offsets:
                continue

            offset = (
                synchronization.offsets[
                    camera.id
                ]
            )

            # ------------------------------------------------
            # Camera starts:
            #
            # source = timeline + offset
            #
            # source = 0
            #
            # timeline = -offset
            # ------------------------------------------------

            camera_start = -offset

            if (
                start
                < camera_start
                < end
            ):

                boundaries.add(
                    round(
                        camera_start,
                        6,
                    )
                )

            # ------------------------------------------------
            # Camera ends.
            # ------------------------------------------------

            if camera.duration > 0:

                camera_end = (
                    camera.duration
                    - offset
                )

                if (
                    start
                    < camera_end
                    < end
                ):

                    boundaries.add(
                        round(
                            camera_end,
                            6,
                        )
                    )

        sorted_boundaries = sorted(
            boundaries
        )

        ranges: list[
            tuple[float, float]
        ] = []

        for index in range(
            len(sorted_boundaries) - 1
        ):

            range_start = (
                sorted_boundaries[index]
            )

            range_end = (
                sorted_boundaries[
                    index + 1
                ]
            )

            if range_end > range_start:

                ranges.append(
                    (
                        range_start,
                        range_end,
                    )
                )

        return ranges

    # ========================================================
    # Find Camera
    # ========================================================

    @staticmethod
    def _find_camera(
        cameras: list[CameraSource],
        camera_id: str,
    ) -> CameraSource:

        for camera in cameras:

            if camera.id == camera_id:
                return camera

        raise EDLValidationError(
            f"Camera {camera_id} does not exist."
        )

    # ========================================================
    # Validate Source Range
    # ========================================================

    @staticmethod
    def _validate_source_range(
        camera: CameraSource,
        source_start: float,
        source_end: float,
        segment_id: str,
        tolerance: float = 0.05,
    ) -> None:

        if source_start < -tolerance:

            raise EDLValidationError(
                "SOURCE_RANGE_INVALID: "
                f"Segment {segment_id} starts at "
                f"{source_start:.3f}s in "
                f"{camera.id}."
            )

        if source_end <= source_start:

            raise EDLValidationError(
                "SOURCE_RANGE_INVALID: "
                f"Segment {segment_id} has an invalid "
                "source range."
            )

        if camera.duration > 0:

            if (
                source_end
                > camera.duration + tolerance
            ):

                raise EDLValidationError(
                    "SOURCE_RANGE_INVALID: "
                    f"Segment {segment_id} ends at "
                    f"{source_end:.3f}s, but "
                    f"{camera.id} duration is "
                    f"{camera.duration:.3f}s."
                )

    # ========================================================
    # Build Vision Reason
    # ========================================================

    def _build_vision_reason(
        self,
        shot: dict[str, Any],
        camera: CameraSource,
        timeline_results: list[
            tuple[
                float,
                list[Any],
            ]
        ],
    ) -> str:

        start = float(
            shot["start"]
        )

        end = float(
            shot["end"]
        )

        relevant = []

        for timeline_time, analyses in (
            timeline_results
        ):

            if (
                start
                <= timeline_time
                <= end
            ):

                for analysis in analyses:

                    if (
                        analysis.camera_id
                        == camera.id
                    ):

                        relevant.append(
                            analysis
                        )

        if not relevant:

            return (
                f"{camera.name} was selected by "
                "automatic vision analysis."
            )

        average_score = (
            sum(
                item.total_score
                for item in relevant
            )
            / len(relevant)
        )

        average_subject_size = (
            sum(
                item.main_subject_area_ratio
                for item in relevant
            )
            / len(relevant)
        )

        average_sharpness = (
            sum(
                item.sharpness_score
                for item in relevant
            )
            / len(relevant)
        )

        average_motion = (
            sum(
                item.motion_score
                for item in relevant
            )
            / len(relevant)
        )

        return (
            f"{camera.name} selected by automatic "
            f"vision analysis. "
            f"Average vision score: "
            f"{average_score:.1f}/100; "
            f"main subject area: "
            f"{average_subject_size:.1%}; "
            f"sharpness: "
            f"{average_sharpness:.2f}; "
            f"motion: "
            f"{average_motion:.2f}."
        )

    # ========================================================
    # Merge Adjacent Same-Camera Segments
    # ========================================================

    @staticmethod
    def _merge_adjacent_same_camera_segments(
        segments: list[EDLSegment],
    ) -> list[EDLSegment]:

        if not segments:
            return []

        merged = [
            segments[0]
        ]

        for current in segments[1:]:

            previous = merged[-1]

            same_camera = (
                previous.selected_camera
                == current.selected_camera
            )

            adjacent = (
                abs(
                    previous.timeline_end
                    - current.timeline_start
                )
                < 0.000001
            )

            same_event = (
                previous.event_type
                == current.event_type
            )

            not_manual = (
                not previous.manually_modified
                and not current.manually_modified
            )

            if (
                same_camera
                and adjacent
                and same_event
                and not_manual
            ):

                merged[-1] = EDLSegment(
                    id=previous.id,
                    timeline_start=(
                        previous.timeline_start
                    ),
                    timeline_end=(
                        current.timeline_end
                    ),
                    selected_camera=(
                        previous.selected_camera
                    ),
                    source_start=(
                        previous.source_start
                    ),
                    source_end=(
                        current.source_end
                    ),
                    event_type=(
                        previous.event_type
                    ),
                    description=(
                        previous.description
                    ),
                    reason=(
                        previous.reason
                    ),
                    transition=(
                        previous.transition
                    ),
                    overlay=(
                        previous.overlay
                    ),
                    approved=False,
                    manually_modified=False,
                )

            else:

                merged.append(
                    current
                )

        return merged

    # ========================================================
    # Apply Transitions
    # ========================================================

    @staticmethod
    def _apply_transitions(
        segments: list[EDLSegment],
    ) -> list[EDLSegment]:

        if not segments:
            return []

        result = []

        for index, segment in enumerate(
            segments
        ):

            transition = (
                "fade"
                if index == 0
                else "cut"
            )

            result.append(
                replace(
                    segment,
                    transition=transition,
                )
            )

        return result

    # ========================================================
    # Human Review: Update Segment
    # ========================================================

    def update_segment(
        self,
        segment: EDLSegment,
        changes: dict[str, Any],
    ) -> EDLSegment:

        valid_fields = set(
            segment.__dataclass_fields__
        )

        unknown = (
            set(changes)
            - valid_fields
        )

        if unknown:

            raise ValueError(
                "Unknown EDL fields: "
                + ", ".join(
                    sorted(unknown)
                )
            )

        changed_materially = any(
            key in MATERIAL_FIELDS
            and getattr(
                segment,
                key,
            ) != value
            for key, value in changes.items()
        )

        values = dict(
            changes
        )

        if isinstance(
            values.get("overlay"),
            dict,
        ):

            values["overlay"] = Overlay(
                **values["overlay"]
            )

        if changed_materially:

            values["approved"] = False

            values[
                "manually_modified"
            ] = True

        return replace(
            segment,
            **values,
        )

    # ========================================================
    # Save
    # ========================================================

    def save(
        self,
        path: Path,
        project: Project,
        cameras: list[CameraSource],
        segments: list[EDLSegment],
        subtitles: list[Any] | None = None,
    ) -> None:

        atomic_write_json(
            path,
            {
                "schema_version": "1.0",

                "project": to_dict(
                    project
                ),

                "cameras": [
                    to_dict(camera)
                    for camera in cameras
                ],

                "segments": [
                    to_dict(segment)
                    for segment in segments
                ],

                "subtitles": [
                    to_dict(item)
                    for item in (
                        subtitles or []
                    )
                ],
            },
        )

    # ========================================================
    # Load
    # ========================================================

    def load_segments(
        self,
        path: Path,
    ) -> list[EDLSegment]:

        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        return [
            edl_from_dict(item)
            for item in data[
                "segments"
            ]
        ]

    # ========================================================
    # Export EDL Decisions CSV
    # ========================================================

    def export_decisions(
        self,
        path: Path,
        segments: list[EDLSegment],
    ) -> None:

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as handle:

            writer = csv.writer(
                handle
            )

            writer.writerow(
                [
                    "segment_id",
                    "timeline_start",
                    "timeline_end",
                    "camera",
                    "source_start",
                    "source_end",
                    "event_type",
                    "transition",
                    "reason",
                    "approved",
                ]
            )

            for segment in segments:

                writer.writerow(
                    [
                        segment.id,
                        f"{segment.timeline_start:.3f}",
                        f"{segment.timeline_end:.3f}",
                        segment.selected_camera,
                        f"{segment.source_start:.3f}",
                        f"{segment.source_end:.3f}",
                        segment.event_type,
                        segment.transition,
                        segment.reason,
                        segment.approved,
                    ]
                )

    # ========================================================
    # Diagnostic
    # ========================================================

    def diagnose(
        self,
        cameras: list[CameraSource],
        programme: list[ProgrammeSegment],
        synchronization: SynchronizationConfig,
    ) -> list[dict[str, Any]]:

        diagnostics = []

        for item in programme:

            available = (
                get_available_cameras(
                    cameras=cameras,
                    timeline_start=item.start,
                    timeline_end=item.end,
                    synchronization=synchronization,
                )
            )

            camera_status = {}

            for camera in cameras:

                camera_status[
                    camera.id
                ] = camera_is_available(
                    camera,
                    item.start,
                    item.end,
                    synchronization,
                )

            diagnostics.append(
                {
                    "segment_id": item.id,

                    "timeline_start": (
                        item.start
                    ),

                    "timeline_end": (
                        item.end
                    ),

                    "available_cameras": [
                        camera.id
                        for camera in available
                    ],

                    "camera_status": (
                        camera_status
                    ),
                }
            )

        return diagnostics

    # ========================================================
    # Cleanup
    # ========================================================

    def close(self) -> None:

        if self.vision_analyzer:

            self.vision_analyzer.close()