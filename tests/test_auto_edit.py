from __future__ import annotations

import sys
from pathlib import Path


# ============================================================
# Make sure src/ is importable
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from vcut.models import CameraSource, SynchronizationConfig
from vcut.vision_analyzer import VisionAnalyzer
from vcut.switch_engine import SwitchEngine


# ============================================================
# CONFIGURATION
# ============================================================

# ------------------------------------------------------------
# Camera video files
# ------------------------------------------------------------
#
# If the MP4 files are in the project root:
#
#     Camera1-1.mp4
#     Camera2-1.mp4
#     Camera3-1.mp4
#     Camera4-1.mp4
#
# use the paths below.
#
# If they are somewhere else, replace them with the FULL path.
# ------------------------------------------------------------

CAMERA_FILES = {
    "CAM001": PROJECT_ROOT / "Camera1-1.mp4",
    "CAM002": PROJECT_ROOT / "Camera2-1.mp4",
    "CAM003": PROJECT_ROOT / "Camera3-1.mp4",
    "CAM004": PROJECT_ROOT / "Camera4-1.mp4",
}


# ------------------------------------------------------------
# Camera information
# ------------------------------------------------------------
#
# IMPORTANT:
#
# Replace durations if your actual recordings have different
# durations.
#
# These values should ideally come from your Camera Import
# stage.
# ------------------------------------------------------------

CAMERA_INFO = {
    "CAM001": {
        "name": "Camera 1",
        "role": "wide",
        "duration": 125.109,
    },

    "CAM002": {
        "name": "Camera 2",
        "role": "front",
        "duration": 43.050,
    },

    "CAM003": {
        "name": "Camera 3",
        "role": "front_left",
        "duration": 95.713,
    },

    "CAM004": {
        "name": "Camera 4",
        "role": "front",
        "duration": 97.106,
    },
}


# ------------------------------------------------------------
# Synchronization
# ------------------------------------------------------------
#
# Based on the synchronization structure we have been using:
#
# CAM001 = reference
# CAM002 = -57
# CAM003 = -8
# CAM004 = -18
#
# source_time = timeline_time + offset
#
# Example:
#
# Timeline 65s:
#
# CAM001 = 65
# CAM002 = 8
# CAM003 = 57
# CAM004 = 47
# ------------------------------------------------------------

SYNCHRONIZATION = SynchronizationConfig(
    reference_camera_id="CAM001",

    clap_times={
        "CAM001": 57.0,
        "CAM002": 0.0,
        "CAM003": 49.0,
        "CAM004": 39.0,
    },

    offsets={
        "CAM001": 0.0,
        "CAM002": -57.0,
        "CAM003": -8.0,
        "CAM004": -18.0,
    },

    approved=True,
)


# ============================================================
# PROGRAMME RANGE
# ============================================================
#
# CHANGE THESE TWO VALUES to the section of your video that
# you want to test.
#
# Example:
#
#     57 -> 100
#
# means:
#
#     Analyse Timeline 57s through 100s.
# ============================================================

TIMELINE_START = 57.0
TIMELINE_END = 100.0


# ============================================================
# ANALYSIS SETTINGS
# ============================================================

# Look at the video every 0.5 seconds.
#
# Again:
#
#     This is NOT a cut every 0.5 seconds.
#
# SwitchEngine decides whether a real switch is necessary.
ANALYSIS_INTERVAL = 0.5


# Minimum shot duration.
MIN_SHOT_DURATION = 3.0


# Candidate must beat current camera by this amount.
SWITCH_MARGIN = 8.0


# Candidate must remain better for this amount of time.
CONFIRMATION_DURATION = 1.5


# Score smoothing.
SMOOTHING_ALPHA = 0.35


# ============================================================
# CREATE CAMERA OBJECTS
# ============================================================


def build_cameras() -> list[CameraSource]:
    """
    Build CameraSource objects from the configuration.
    """

    cameras = []

    for camera_id, info in CAMERA_INFO.items():

        video_path = CAMERA_FILES[
            camera_id
        ]

        cameras.append(
            CameraSource(
                id=camera_id,

                name=info["name"],

                role=info["role"],

                file=str(
                    video_path
                ),

                duration=float(
                    info["duration"]
                ),

                width=1280,

                height=720,

                fps=30.0,

                codec="h264",

                has_audio=True,

                file_size=(
                    video_path.stat().st_size
                    if video_path.exists()
                    else 0
                ),
            )
        )

    return cameras


# ============================================================
# CHECK FILES
# ============================================================


def check_video_files() -> bool:
    """
    Check whether all four MP4 files exist.
    """

    print()
    print("=" * 70)
    print("CHECKING CAMERA FILES")
    print("=" * 70)

    all_exist = True

    for camera_id, path in CAMERA_FILES.items():

        if path.exists():

            size_mb = (
                path.stat().st_size
                / (
                    1024 * 1024
                )
            )

            print(
                f"✓ {camera_id}: "
                f"{path}"
            )

            print(
                f"  Size: "
                f"{size_mb:.2f} MB"
            )

        else:

            print(
                f"✗ {camera_id}: "
                f"FILE NOT FOUND"
            )

            print(
                f"  Expected: "
                f"{path}"
            )

            all_exist = False

    print()

    return all_exist


# ============================================================
# PRINT FRAME ANALYSIS
# ============================================================


def print_frame_analysis(
    timeline_time: float,
    analyses,
) -> None:
    """
    Print the Camera scores at one timeline time.
    """

    print()
    print(
        f"TIME {timeline_time:7.2f}s"
    )

    print("-" * 70)

    if not analyses:

        print(
            "  No valid cameras available."
        )

        return

    for index, analysis in enumerate(
        analyses
    ):

        marker = (
            "★"
            if index == 0
            else " "
        )

        print(
            f"{marker} "
            f"{analysis.camera_id}  "
            f"score={analysis.total_score:6.2f}  "
            f"persons={analysis.person_count:<2}  "
            f"subject={analysis.main_subject_area_ratio:6.2%}  "
            f"sharp={analysis.sharpness_score:5.2f}  "
            f"motion={analysis.motion_score:5.2f}"
        )


# ============================================================
# MAIN
# ============================================================


def main() -> int:

    print()
    print("=" * 70)
    print("VCut AUTOMATIC CAMERA TEST")
    print("=" * 70)

    print()
    print(
        f"Timeline: "
        f"{TIMELINE_START:.2f}s "
        f"→ "
        f"{TIMELINE_END:.2f}s"
    )

    print(
        f"Analysis interval: "
        f"{ANALYSIS_INTERVAL:.2f}s"
    )

    print(
        f"Minimum shot duration: "
        f"{MIN_SHOT_DURATION:.2f}s"
    )

    print(
        f"Switch margin: "
        f"{SWITCH_MARGIN:.2f}"
    )

    print(
        f"Confirmation duration: "
        f"{CONFIRMATION_DURATION:.2f}s"
    )

    # --------------------------------------------------------
    # Check files
    # --------------------------------------------------------

    if not check_video_files():

        print()
        print(
            "ERROR: One or more Camera video files "
            "are missing."
        )

        print()
        print(
            "Please edit CAMERA_FILES in "
            "test_auto_edit.py."
        )

        return 1

    # --------------------------------------------------------
    # Build cameras
    # --------------------------------------------------------

    cameras = build_cameras()

    # --------------------------------------------------------
    # Create VisionAnalyzer
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("LOADING VISION ANALYZER")
    print("=" * 70)

    print()
    print(
        "YOLO will be loaded when the first frame "
        "is analysed."
    )

    analyzer = VisionAnalyzer()

    # --------------------------------------------------------
    # Create SwitchEngine
    # --------------------------------------------------------

    switch_engine = SwitchEngine(
        min_shot_duration=MIN_SHOT_DURATION,

        switch_margin=SWITCH_MARGIN,

        confirmation_duration=(
            CONFIRMATION_DURATION
        ),

        smoothing_alpha=(
            SMOOTHING_ALPHA
        ),

        analysis_interval=(
            ANALYSIS_INTERVAL
        ),
    )

    # --------------------------------------------------------
    # Analyse timeline
    # --------------------------------------------------------

    timeline_results = []

    current_time = (
        TIMELINE_START
    )

    try:

        print()
        print("=" * 70)
        print("VISION ANALYSIS")
        print("=" * 70)

        while (
            current_time
            <= TIMELINE_END
            + 0.000001
        ):

            print(
                f"\rAnalysing "
                f"{current_time:.1f}s...",
                end="",
                flush=True,
            )

            analyses = (
                analyzer.analyze_timeline(
                    timeline_time=current_time,

                    cameras=cameras,

                    synchronization=(
                        SYNCHRONIZATION
                    ),
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
                ANALYSIS_INTERVAL
            )

        print()
        print()

        if not timeline_results:

            print(
                "ERROR: No frames could be analysed."
            )

            return 1

        # ----------------------------------------------------
        # Print results
        # ----------------------------------------------------

        print(
            f"Successfully analysed "
            f"{len(timeline_results)} "
            f"timeline points."
        )

        # ----------------------------------------------------
        # Optional detailed output
        # ----------------------------------------------------
        #
        # This prints every analysis point.
        #
        # If there are many points, you can comment this
        # section out later.
        # ----------------------------------------------------

        for (
            timeline_time,
            analyses,
        ) in timeline_results:

            print_frame_analysis(
                timeline_time,
                analyses,
            )

        # ----------------------------------------------------
        # Determine initial camera
        # ----------------------------------------------------

        first_time, first_analyses = (
            timeline_results[0]
        )

        initial_camera = max(
            first_analyses,

            key=lambda item:
            item.total_score,
        )

        initial_camera_id = "CAM001"

        # ----------------------------------------------------
        # Run SwitchEngine
        # ----------------------------------------------------

        print()
        print("=" * 70)
        print("AUTOMATIC CAMERA SWITCH DECISIONS")
        print("=" * 70)

        switch_result = (
            switch_engine.analyze(
                timeline_results=(
                    timeline_results
                ),

                timeline_start=(
                    TIMELINE_START
                ),

                timeline_end=(
                    TIMELINE_END
                ),

                initial_camera_id=(
                    initial_camera_id
                ),
            )
        )

        # ----------------------------------------------------
        # Print initial camera
        # ----------------------------------------------------

        print()
        print(
            f"Initial Camera: "
            f"{switch_result['initial_camera']}"
        )

        # ----------------------------------------------------
        # Print decisions
        # ----------------------------------------------------

        decisions = (
            switch_result[
                "decisions"
            ]
        )

        if not decisions:

            print()
            print(
                "NO CAMERA SWITCHES."
            )

            print(
                "The current camera remained "
                "the best choice for the entire "
                "tested range."
            )

        else:

            print()

            for index, decision in enumerate(
                decisions,
                start=1,
            ):

                print(
                    f"{index}. "
                    f"{decision['timeline_time']:.2f}s  "
                    f"{decision['from_camera']} "
                    f"→ "
                    f"{decision['to_camera']}"
                )

                print(
                    f"   Current score: "
                    f"{decision['current_score']:.2f}"
                )

                print(
                    f"   Candidate score: "
                    f"{decision['candidate_score']:.2f}"
                )

                print(
                    f"   Difference: "
                    f"{decision['score_difference']:.2f}"
                )

                print(
                    f"   Forced: "
                    f"{decision['forced']}"
                )

                print(
                    f"   Reason: "
                    f"{decision['reason']}"
                )

                print()

        # ----------------------------------------------------
        # Print final EDL-like shot segments
        # ----------------------------------------------------

        print()
        print("=" * 70)
        print("AUTOMATIC CAMERA EDL")
        print("=" * 70)

        segments = (
            switch_result[
                "segments"
            ]
        )

        print()

        print(
            f"{'START':>10} "
            f"{'END':>10} "
            f"{'DURATION':>10} "
            f"{'CAMERA':>10}"
        )

        print(
            "-" * 50
        )

        for segment in segments:

            duration = (
                segment["end"]
                - segment["start"]
            )

            print(
                f"{segment['start']:10.2f} "
                f"{segment['end']:10.2f} "
                f"{duration:10.2f} "
                f"{segment['camera_id']:>10}"
            )

        # ----------------------------------------------------
        # Summary
        # ----------------------------------------------------

        print()
        print("=" * 70)
        print("SUMMARY")
        print("=" * 70)

        print(
            f"Timeline: "
            f"{TIMELINE_START:.2f}s "
            f"→ "
            f"{TIMELINE_END:.2f}s"
        )

        print(
            f"Analysed points: "
            f"{len(timeline_results)}"
        )

        print(
            f"Initial camera: "
            f"{switch_result['initial_camera']}"
        )

        print(
            f"Camera switches: "
            f"{switch_result['switch_count']}"
        )

        print(
            f"Final shots: "
            f"{len(segments)}"
        )

        used_cameras = sorted(
            {
                segment["camera_id"]
                for segment in segments
            }
        )

        print(
            "Cameras used: "
            + ", ".join(
                used_cameras
            )
        )

        print()
        print(
            "Automatic camera selection completed."
        )

        return 0

    except KeyboardInterrupt:

        print()
        print()
        print(
            "Analysis cancelled by user."
        )

        return 130

    except Exception as exc:

        print()
        print()
        print("=" * 70)
        print("ERROR")
        print("=" * 70)

        print(
            type(exc).__name__
            + ": "
            + str(exc)
        )

        print()
        print(
            "Check:"
        )

        print(
            "1. Camera MP4 paths"
        )

        print(
            "2. Synchronization offsets"
        )

        print(
            "3. Camera durations"
        )

        print(
            "4. YOLO / Ultralytics installation"
        )

        print(
            "5. OpenCV installation"
        )

        return 1

    finally:

        analyzer.close()


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    raise SystemExit(
        main()
    )