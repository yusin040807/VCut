# from __future__ import annotations

# from .exceptions import SynchronizationError
# from .models import SynchronizationConfig


# class SynchronizationService:
#     def calculate_offsets(self, clap_times: dict[str, float], reference_camera_id: str) -> SynchronizationConfig:
#         if reference_camera_id not in clap_times:
#             raise SynchronizationError("Select a reference camera with a clap timestamp.")
#         if len(clap_times) < 2:
#             raise SynchronizationError("At least two camera clap timestamps are required.")
#         if any(value < 0 for value in clap_times.values()):
#             raise SynchronizationError("Clap timestamps cannot be negative.")
#         reference = clap_times[reference_camera_id]
#         offsets = {camera_id: round(value - reference, 6) for camera_id, value in clap_times.items()}
#         return SynchronizationConfig(reference_camera_id, dict(clap_times), offsets)

#     def timeline_to_source_time(self, timeline_time: float, camera_id: str, synchronization: SynchronizationConfig) -> float:
#         if camera_id not in synchronization.offsets:
#             raise SynchronizationError(f"Camera {camera_id} has no synchronization offset.")
#         value = timeline_time + synchronization.offsets[camera_id]
#         if value < 0:
#             raise SynchronizationError(f"Timeline time maps before the start of camera {camera_id}.")
#         return round(value, 6)

from __future__ import annotations

from .exceptions import SynchronizationError
from .models import SynchronizationConfig


class SynchronizationService:

    def calculate_offsets(
        self,
        clap_times: dict[str, float],
        reference_camera_id: str,
    ) -> SynchronizationConfig:

        if reference_camera_id not in clap_times:
            raise SynchronizationError(
                "Select a reference camera with a clap timestamp."
            )

        if len(clap_times) < 2:
            raise SynchronizationError(
                "At least two camera clap timestamps are required."
            )

        if any(value < 0 for value in clap_times.values()):
            raise SynchronizationError(
                "Clap timestamps cannot be negative."
            )

        reference = clap_times[reference_camera_id]

        offsets = {
            camera_id: round(
                value - reference,
                6,
            )
            for camera_id, value in clap_times.items()
        }

        return SynchronizationConfig(
            reference_camera_id=reference_camera_id,
            clap_times=dict(clap_times),
            offsets=offsets,
        )

    def timeline_to_source_time(
        self,
        timeline_time: float,
        camera_id: str,
        synchronization: SynchronizationConfig,
    ) -> float:

        if timeline_time < 0:
            raise SynchronizationError(
                "Timeline time cannot be negative."
            )

        if camera_id not in synchronization.offsets:
            raise SynchronizationError(
                f"Camera {camera_id} has no synchronization offset."
            )

        value = (
            timeline_time
            + synchronization.offsets[camera_id]
        )

        if value < 0:
            raise SynchronizationError(
                f"Timeline time maps before the start "
                f"of camera {camera_id}."
            )

        return round(
            value,
            6,
        )