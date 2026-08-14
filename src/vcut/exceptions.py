class VCutError(Exception):
    """Base user-facing VCut error."""


class ProjectError(VCutError):
    pass


class MediaProbeError(VCutError):
    pass


class SynchronizationError(VCutError):
    pass


class ProgrammeFormatError(VCutError):
    pass


class SubtitleFormatError(VCutError):
    pass


class EDLValidationError(VCutError):
    pass


class RenderError(VCutError):
    pass


class DependencyError(VCutError):
    pass
