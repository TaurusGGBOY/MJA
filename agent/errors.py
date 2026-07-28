from enum import StrEnum


class ErrorCode(StrEnum):
    """Stable machine-readable failure codes for an MJA run."""

    PERMISSION_SCREEN_CAPTURE = "PERMISSION_SCREEN_CAPTURE"
    PERMISSION_ACCESSIBILITY = "PERMISSION_ACCESSIBILITY"
    APP_LAUNCH_TIMEOUT = "APP_LAUNCH_TIMEOUT"
    WINDOW_NOT_FOUND = "WINDOW_NOT_FOUND"
    WINDOW_RESIZE_FAILED = "WINDOW_RESIZE_FAILED"
    CONTROLLER_CONNECT_FAILED = "CONTROLLER_CONNECT_FAILED"
    CONTROLLER_PROBE_FAILED = "CONTROLLER_PROBE_FAILED"
    HOME_RECOGNITION_TIMEOUT = "HOME_RECOGNITION_TIMEOUT"
    MAIL_OPEN_TIMEOUT = "MAIL_OPEN_TIMEOUT"
    HOME_RETURN_TIMEOUT = "HOME_RETURN_TIMEOUT"
    WINDOW_RESTORE_FAILED = "WINDOW_RESTORE_FAILED"


class MJAError(RuntimeError):
    """An expected, diagnosable failure in an MJA run."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code.value, "message": str(self)}
