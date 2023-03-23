"""Supported cloud endpoints."""
from __future__ import annotations

WORX = "worx"
KRESS = "kress"
LANDXCAPE = "landxcape"


class CloudType(object):
    """Supported cloud types.

    CloudType.WORX: For Worx Landroid devices.

    CloudType.KRESS: For Kress devices.

    CloudType.LANDXCAPE: For Landxcape devices.
    """

    class WORX(str):
        """Settings for Worx devices."""

        URL: str = "api.worxlandroid.com"
        TOKEN_URL: str = "id.eu.worx.com"
        KEY: str = "150da4d2-bb44-433b-9429-3773adc70a2a"

    class KRESS(str):
        """Settings for Kress devices."""

        URL: str = "api.kress-robotik.com"
        TOKEN_URL: str = "id.eu.kress.com"
        KEY: str = "931d4bc4-3192-405a-be78-98e43486dc59"

    class LANDXCAPE(str):
        """Settings for Landxcape devices."""

        URL: str = "api.landxcape-services.com"
        TOKEN_URL: str = "id.landxcape-services.com"
        KEY: str = "dec998a9-066f-433b-987a-f5fc54d3af7c"
