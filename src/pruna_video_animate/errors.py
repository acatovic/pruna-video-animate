class PrunaError(Exception):
    """Base error for Pruna video animation failures."""


class PrunaAuthError(PrunaError):
    """Raised when authentication configuration is missing or invalid."""


class PrunaUploadError(PrunaError):
    """Raised when uploading an input file fails."""


class PrunaPredictionError(PrunaError):
    """Raised when prediction creation or status polling fails."""


class PrunaTimeoutError(PrunaError):
    """Raised when prediction polling exceeds the configured timeout."""


class PrunaDownloadError(PrunaError):
    """Raised when downloading or validating the generated MP4 fails."""
