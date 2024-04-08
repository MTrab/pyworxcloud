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

        BRAND_PREFIX: str = "WX"
        ENDPOINT: str = "api.worxlandroid.com"
        AUTH_ENDPOINT: str = "id.worx.com"
        AUTH_CLIENT_ID: str = "150da4d2-bb44-433b-9429-3773adc70a2a"

    class KRESS(str):
        """Settings for Kress devices."""

        BRAND_PREFIX: str = "KR"
        ENDPOINT: str = "api.kress-robotik.com"
        AUTH_ENDPOINT: str = "id.kress.com"
        AUTH_CLIENT_ID: str = "931d4bc4-3192-405a-be78-98e43486dc59"

    class LANDXCAPE(str):
        """Settings for Landxcape devices."""

        BRAND_PREFIX: str = "LX"
        ENDPOINT: str = "api.landxcape-services.com"
        AUTH_ENDPOINT: str = "id.landxcape-services.com"
        AUTH_CLIENT_ID: str = "dec998a9-066f-433b-987a-f5fc54d3af7c"
