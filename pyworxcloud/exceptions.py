"""Landroid Cloud exception definitions."""
from __future__ import annotations


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


class MQTTException(Exception):
    """Define a MQTT exception."""


class RateLimit(Exception):
    """Defines a ratelimit exception."""

    def __init__(self, message):
        """Custom ratelimit exception class"""
        super(RateLimit, self).__init__(message)
        self.message = message


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
