class LMSExtractError(Exception):
    """Base exception for expected CLI failures."""


class ConfigError(LMSExtractError):
    """Configuration is missing or invalid."""


class AuthError(LMSExtractError):
    """Authentication failed."""


class MoodleParseError(LMSExtractError):
    """Moodle HTML could not be parsed as expected."""


class DownloadError(LMSExtractError):
    """A resource could not be downloaded."""

