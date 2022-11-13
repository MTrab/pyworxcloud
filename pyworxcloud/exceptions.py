"""Landroid Cloud exception definitions."""
from __future__ import annotations


class TokenError(Exception):
    """Error raised when no auth or refresh token is found."""


class RequestError(Exception):
    """Error representing a request error."""


class AuthorizationError(Exception):
    """Error representing an authorization error."""


class ForbiddenError(Exception):
    """Error representing an access forbidden error."""


class NotFoundError(Exception):
    """Error representing an endpoint not found error."""


class TooManyRequestsError(Exception):
    """Error representing a too many redirects error."""


class InternalServerError(Exception):
    """Error representing an internal server error."""


class ServiceUnavailableError(Exception):
    """Error representing a service unavailable error."""


class APIError(Exception):
    """Error representing a generic API error."""


class MowerNotFoundError(Exception):
    """Error raised when a specific requested mower was not found in the result."""
