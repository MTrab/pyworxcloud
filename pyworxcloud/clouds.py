"""Supported cloud endpoints."""
from __future__ import annotations

from enum import Enum
from typing import Dict

WORX = "worx"
KRESS = "kress"
LANDXCAPE = "landxcape"
FERREX = "ferrex"


class CloudType(object):
    """Supported cloud types.

    CloudType.WORX: For Worx Landroid devices.

    CloudType.KRESS: For Kress devices.

    CloudType.LANDXCAPE: For Landxcape devices.

    CloudType.FERREX: For Aldi Ferrex devices.
    """

    class WORX(str):
        """Settings for Worx devices."""

        URL: str = "api.worxlandroid.com"

        KEY: str = "nCH3A0WvMYn66vGorjSrnGZ2YtjQWDiCvjg7jNxK"

    class KRESS(str):
        """Settings for Kress devices."""

        URL: str = "api.kress-robotik.com"

        KEY: str = "t2ANJxvWuVoAZSTw4gdrD2cy37dEwqtQSUxxY02q"

    class LANDXCAPE(str):
        """Settings for Landxcape devices."""

        URL: str = "api.landxcape-services.com"

        KEY: str = "UKDRabKqJFNZYBAHW3GJDfgrDcZEQNYwkNHE8XSP"

    class FERREX(str):
        """Settings for Aldi Ferrex devices."""

        URL: str = "api.watermelon.smartmower.cloud"

        KEY: str = "xZY9IAxGAqe1wpMRKA39M9gRkLfX6IW5zbgwCi0E"
