"""Module specific exceptions."""

class BadRequest(Exception):
    pass

class UnauthorizedError(Exception):
    pass

class APIEndpointError(Exception):
    pass

class InternalServerError(Exception):
    pass

class ServiceUnavailableError(Exception):
    pass

class UnknownError(Exception):
    pass