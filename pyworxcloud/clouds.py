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

        KEY: str = "725f542f5d2c4b6a5145722a2a6a5b736e764f6e725b462e4568764d4b58755f6a767b2b76526457"

    class KRESS(str):
        """Settings for Kress devices."""

        URL: str = "api.kress-robotik.com"

        KEY: str = "5a1c6f60645658795b78416f747d7a591a494a5c6a1c4d571d194a6b595f5a7f7d7b5656771e1c5f"

    class LANDXCAPE(str):
        """Settings for Landxcape devices."""

        URL: str = "api.landxcape-services.com"

        KEY: str = "071916003330192318141c080b10131a056115181634352016310817031c0b25391c1a176a0a0102"

    class FERREX(str):
        """Settings for Aldi Ferrex devices."""

        URL: str = "api.watermelon.smartmower.cloud"

        KEY: str = "xZY9IAxGAqe1wpMRKA39M9gRkLfX6IW5zbgwCi0E"
