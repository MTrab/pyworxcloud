"""Simple utility that demonstrates how to instrument the shared HTTP session."""

from __future__ import annotations

import logging

from pyworxcloud.utils.requests import create_session

logger = logging.getLogger("pyworxcloud.session_trace")
logging.basicConfig(level=logging.INFO)


def _log_response(response, *args, **kwargs):
    logger.info(
        "HTTP %s %s -> %s (%s bytes)",
        response.request.method,
        response.request.url,
        response.status_code,
        len(response.content),
    )


def main() -> None:
    """Example: add a hook to the retry session and execute a request."""
    session = create_session()
    session.hooks["response"].append(_log_response)

    logger.info("Sending GET to example API")
    resp = session.get("https://httpbin.org/status/200")
    resp.raise_for_status()

    logger.info("Now you can reuse `session` for instrumented requests.")


if __name__ == "__main__":
    main()
