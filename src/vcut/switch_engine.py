from __future__ import annotations

from dataclasses import dataclass
from typing import Any


MAIN_CAMERA_ID = "CAM001"


@dataclass
class SwitchCandidate:
    camera_id: str
    since: float


class SwitchEngine:
    """
    Decide when the edited video should switch cameras.

    Main-camera policy:
        CAM001 is the default/main camera.

    The engine will switch away from CAM001 only when another
    camera is clearly and consistently better.

    It will NOT:
        - switch at fixed time intervals
        - force camera changes just to create variety
        - switch because another camera is only slightly better
        - immediately switch back and forth
    """

    def __init__(
        self,
        min_shot_duration: float = 3.0,
        switch_margin: float = 5.0,
        confirmation_duration: float = 1.5,
        smoothing_alpha: float = 0.7,
        analysis_interval: float = 0.5,
        main_camera_id: str = "CAM001"
    ):
        self.min_shot_duration = float(
            min_shot_duration
        )

        self.switch_margin = float(
            switch_margin
        )

        self.confirmation_duration = float(
            confirmation_duration
        )

        self.smoothing_alpha = float(
            smoothing_alpha
        )

        self.analysis_interval = float(
            analysis_interval
        )

        self.main_camera_id = main_camera_id

        self.reset()

    # =========================================================
    # State
    # =========================================================

    def reset(self) -> None:
        self.current_camera_id = None
        self.current_shot_start = None

        self.candidate_camera_id = None
        self.candidate_since = None

        self.smoothed_scores: dict[str, float] = {}

    # =========================================================
    # Helpers
    # =========================================================

    @staticmethod
    def _analysis_camera_id(
        analysis: Any,
    ) -> str | None:

        return getattr(
            analysis,
            "camera_id",
            None,
        )

    @staticmethod
    def _analysis_score(
        analysis: Any,
    ) -> float:

        return float(
            getattr(
                analysis,
                "total_score",
                0.0,
            )
        )

    def _smooth_score(
        self,
        camera_id: str,
        score: float,
    ) -> float:

        previous = self.smoothed_scores.get(
            camera_id
        )

        if previous is None:

            smoothed = score

        else:

            alpha = self.smoothing_alpha

            smoothed = (
                alpha * score
                + (1.0 - alpha) * previous
            )

        self.smoothed_scores[
            camera_id
        ] = smoothed

        return smoothed

    def _get_scores(
        self,
        analyses,
    ) -> dict[str, float]:

        scores = {}

        for analysis in analyses:

            camera_id = (
                self._analysis_camera_id(
                    analysis
                )
            )

            if not camera_id:
                continue

            raw_score = (
                self._analysis_score(
                    analysis
                )
            )

            scores[camera_id] = (
                self._smooth_score(
                    camera_id,
                    raw_score,
                )
            )

        return scores

    def _best_camera(
        self,
        scores: dict[str, float],
    ) -> tuple[str | None, float]:

        if not scores:
            return None, float("-inf")

        camera_id = max(
            scores,
            key=scores.get,
        )

        return (
            camera_id,
            scores[camera_id],
        )

    # =========================================================
    # Main-camera aware candidate selection
    # =========================================================

    def _choose_candidate(
        self,
        scores: dict[str, float],
        current_camera_id: str,
    ) -> tuple[str | None, float, float, str]:

        current_score = scores.get(
            current_camera_id
        )

        if current_score is None:

            current_score = float(
                "-inf"
            )

        # -----------------------------------------------------
        # Find the best alternative camera.
        # -----------------------------------------------------

        alternatives = {
            camera_id: score
            for camera_id, score
            in scores.items()
            if camera_id != current_camera_id
        }

        if not alternatives:

            return (
                None,
                current_score,
                float("-inf"),
                "No alternative camera available.",
            )

        candidate_id = max(
            alternatives,
            key=alternatives.get,
        )

        candidate_score = (
            alternatives[candidate_id]
        )

        difference = (
            candidate_score
            - current_score
        )

        # -----------------------------------------------------
        # Main-camera protection
        #
        # CAM001 remains the default unless another camera
        # clearly beats it.
        # -----------------------------------------------------

        if (
            current_camera_id
            == self.main_camera_id
        ):

            if difference < self.switch_margin:

                return (
                    None,
                    current_score,
                    candidate_score,
                    (
                        "Main camera retained; "
                        "no alternative is clearly better."
                    ),
                )

        # -----------------------------------------------------
        # Normal camera-to-camera switching.
        # -----------------------------------------------------

        if difference < self.switch_margin:

            return (
                None,
                current_score,
                candidate_score,
                (
                    "Current camera retained; "
                    "candidate advantage is below "
                    "the switch margin."
                ),
            )

        return (
            candidate_id,
            current_score,
            candidate_score,
            (
                f"{candidate_id} is clearly better "
                f"than {current_camera_id}."
            ),
        )

    # =========================================================
    # Reset candidate
    # =========================================================

    def _clear_candidate(self) -> None:

        self.candidate_camera_id = None
        self.candidate_since = None

    # =========================================================
    # Analyze
    # =========================================================

    def analyze(
        self,
        timeline_results,
        timeline_start: float,
        timeline_end: float,
        initial_camera_id: str | None = None,
    ) -> dict[str, Any]:

        self.reset()

        if not timeline_results:

            return {
                "initial_camera": (
                    initial_camera_id
                    or self.main_camera_id
                ),
                "decisions": [],
                "segments": [],
                "switch_count": 0,
            }

        # -----------------------------------------------------
        # IMPORTANT:
        # CAM001 is always the preferred starting camera.
        #
        # Do not select the highest-scoring camera at the
        # first frame.
        # -----------------------------------------------------

        available_first = (
            timeline_results[0][1]
        )

        first_camera_ids = {
            self._analysis_camera_id(
                analysis
            )
            for analysis in available_first
        }

        if (
            self.main_camera_id
            in first_camera_ids
        ):

            initial_camera = (
                self.main_camera_id
            )

        elif initial_camera_id:

            initial_camera = (
                initial_camera_id
            )

        else:

            initial_camera, _ = (
                self._best_camera(
                    self._get_scores(
                        available_first
                    )
                )
            )

        if initial_camera is None:

            return {
                "initial_camera": (
                    self.main_camera_id
                ),
                "decisions": [],
                "segments": [],
                "switch_count": 0,
            }

        self.current_camera_id = (
            initial_camera
        )

        self.current_shot_start = float(
            timeline_start
        )

        decisions = []

        # -----------------------------------------------------
        # Process every analysis point.
        # -----------------------------------------------------

        for (
            timeline_time,
            analyses,
        ) in timeline_results:

            timeline_time = float(
                timeline_time
            )

            scores = self._get_scores(
                analyses
            )

            if not scores:
                continue

            current_camera = (
                self.current_camera_id
            )

            if current_camera is None:
                continue

            # -------------------------------------------------
            # Current camera may not be available at this
            # timeline point.
            #
            # In that case we are allowed to recover using
            # the best available camera.
            # -------------------------------------------------

            if current_camera not in scores:

                candidate_id, _, _, reason = (
                    self._choose_candidate(
                        scores,
                        current_camera,
                    )
                )

                if candidate_id is not None:

                    if (
                        self.candidate_camera_id
                        != candidate_id
                    ):

                        self.candidate_camera_id = (
                            candidate_id
                        )

                        self.candidate_since = (
                            timeline_time
                        )

                    elif (
                        self.candidate_since
                        is not None
                        and
                        timeline_time
                        - self.candidate_since
                        >= self.confirmation_duration
                    ):

                        self._perform_switch(
                            candidate_id,
                            timeline_time,
                            scores,
                            decisions,
                            forced=True,
                            reason=(
                                "Current camera is "
                                "unavailable; "
                                "switched to the "
                                "best available camera."
                            ),
                        )

                continue

            # -------------------------------------------------
            # Respect minimum shot duration.
            # -------------------------------------------------

            shot_duration = (
                timeline_time
                - float(
                    self.current_shot_start
                )
            )

            if (
                shot_duration
                < self.min_shot_duration
            ):

                self._clear_candidate()
                continue

            # -------------------------------------------------
            # Find a genuinely better camera.
            # -------------------------------------------------

            (
                candidate_id,
                current_score,
                candidate_score,
                reason,
            ) = self._choose_candidate(
                scores,
                current_camera,
            )

            # -------------------------------------------------
            # No good reason to switch.
            # -------------------------------------------------

            if candidate_id is None:

                self._clear_candidate()
                continue

            # -------------------------------------------------
            # Candidate changed.
            # Start confirmation timer.
            # -------------------------------------------------

            if (
                self.candidate_camera_id
                != candidate_id
            ):

                self.candidate_camera_id = (
                    candidate_id
                )

                self.candidate_since = (
                    timeline_time
                )

                continue

            # -------------------------------------------------
            # Candidate is still better.
            # Check confirmation duration.
            # -------------------------------------------------

            if (
                self.candidate_since
                is None
            ):

                self.candidate_since = (
                    timeline_time
                )

                continue

            candidate_duration = (
                timeline_time
                - self.candidate_since
            )

            if (
                candidate_duration
                < self.confirmation_duration
            ):

                continue

            # -------------------------------------------------
            # Confirmed switch.
            # -------------------------------------------------

            self._perform_switch(
                candidate_id,
                timeline_time,
                scores,
                decisions,
                forced=False,
                reason=reason,
            )

        # -----------------------------------------------------
        # Final EDL segments.
        # -----------------------------------------------------

        segments = (
            self._build_segments(
                timeline_start=float(
                    timeline_start
                ),
                timeline_end=float(
                    timeline_end
                ),
                decisions=decisions,
                initial_camera=initial_camera,
            )
        )

        return {
            "initial_camera": initial_camera,
            "decisions": decisions,
            "segments": segments,
            "switch_count": len(
                decisions
            ),
        }

    # =========================================================
    # Perform switch
    # =========================================================

    def _perform_switch(
        self,
        candidate_id: str,
        timeline_time: float,
        scores: dict[str, float],
        decisions: list,
        forced: bool,
        reason: str,
    ) -> None:

        current_camera = (
            self.current_camera_id
        )

        if (
            current_camera is None
            or candidate_id == current_camera
        ):

            self._clear_candidate()
            return

        current_score = scores.get(
            current_camera,
            0.0,
        )

        candidate_score = scores.get(
            candidate_id,
            0.0,
        )

        decisions.append(
            {
                "timeline_time": float(
                    timeline_time
                ),
                "from_camera": (
                    current_camera
                ),
                "to_camera": (
                    candidate_id
                ),
                "current_score": float(
                    current_score
                ),
                "candidate_score": float(
                    candidate_score
                ),
                "score_difference": float(
                    candidate_score
                    - current_score
                ),
                "forced": bool(
                    forced
                ),
                "reason": reason,
            }
        )

        self.current_camera_id = (
            candidate_id
        )

        self.current_shot_start = (
            float(timeline_time)
        )

        self._clear_candidate()

    # =========================================================
    # Build EDL segments
    # =========================================================

    def _build_segments(
        self,
        timeline_start: float,
        timeline_end: float,
        decisions: list,
        initial_camera: str,
    ) -> list[dict[str, Any]]:

        segments = []

        current_camera = (
            initial_camera
        )

        segment_start = (
            timeline_start
        )

        for decision in decisions:

            switch_time = float(
                decision["timeline_time"]
            )

            if switch_time <= segment_start:
                continue

            if switch_time > timeline_end:
                continue

            segments.append(
                {
                    "start": round(
                        segment_start,
                        6,
                    ),
                    "end": round(
                        switch_time,
                        6,
                    ),
                    "camera_id": (
                        current_camera
                    ),
                    "reason": (
                        "Main camera retained."
                        if current_camera
                        == self.main_camera_id
                        else "Automatic camera selection."
                    ),
                }
            )

            current_camera = (
                decision["to_camera"]
            )

            segment_start = (
                switch_time
            )

        # -----------------------------------------------------
        # Final segment
        # -----------------------------------------------------

        if (
            segment_start
            < timeline_end
        ):

            segments.append(
                {
                    "start": round(
                        segment_start,
                        6,
                    ),
                    "end": round(
                        timeline_end,
                        6,
                    ),
                    "camera_id": (
                        current_camera
                    ),
                    "reason": (
                        "Main camera retained."
                        if current_camera
                        == self.main_camera_id
                        else "Automatic camera selection."
                    ),
                }
            )

        return segments