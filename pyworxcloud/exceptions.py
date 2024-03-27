"""Landroid Cloud exception definitions."""

from __future__ import annotations


class InvalidDataDecodeException(Exception):
    """Raised when there was an error decoding data."""


class NoPartymodeError(Exception):
    """Define an error when partymode is not supported."""


class NoOneTimeScheduleError(Exception):
    """Define an error when OTS is not supported."""


class OfflineError(Exception):
    """Define an offline error."""


class TokenError(Exception):
    """Define an token error."""


class APIException(Exception):
    """Define an error when communicating with the API."""


class TimeoutException(Exception):
    """Define a timeout error."""


class RequestException(Exception):
    """Define a request exception."""


class RateLimit(Exception):
    """Defines a ratelimit exception."""

    def __init__(self, message):
        """Custom ratelimit exception class"""
        super(RateLimit, self).__init__(message)
        self.message = message


class MQTTException(Exception):
    """Defines a MQTT exception."""


# Exception classes for URL requests
class RequestError(Exception):
    """Define a bad request error (400)."""


class AuthorizationError(Exception):
    """Represents an authorization error (401)."""


class ForbiddenError(Exception):
    """Represents an access forbidden error (403)."""


class NotFoundError(Exception):
    """Represents a not found error (404)."""


class TooManyRequestsError(Exception):
    """Represents a error when request quota have been exceeded (429)."""


class InternalServerError(Exception):
    """Represents an internal server error (500)."""


class ServiceUnavailableError(Exception):
    """Represents a service unavailable error (503)."""


class APIError(Exception):
    """Error representing a generic API error."""


class MowerNotFoundError(Exception):
    """Error raised when a specific requested mower was not found in the result."""


class NoConnectionError(Exception):
    """Raised when the endpoint cannot be reached."""


class ZoneNotDefined(Exception):
    """Raised when the requested zone is not defined."""


class ZoneNoProbability(Exception):
    """Raised when the requested zone is has no probability set."""
