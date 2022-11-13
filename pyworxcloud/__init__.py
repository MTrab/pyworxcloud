"""IoT mower platform module - Positec/Worx/Kress/Landxcape."""
from __future__ import annotations
import json

from .handlers.mqtt import MQTT
from .handlers.requests import GET, HEADERS

from .exceptions import MowerNotFoundError, TokenError
from .token import Token
from .endpoints import CloudType


class WorxCloud:
    """Class of WorxCloud."""

    def __init__(
        self,
        email: str,
        password: str,
        cloud: CloudType.WORX
        | CloudType.KRESS
        | CloudType.LANDXCAPE
        | str = CloudType.WORX,
    ) -> None:
        """Initialize a WorxCloud object."""
        self._email = email
        self._password = password

        self.mowers = []

        if isinstance(cloud, str):
            try:
                cloud = getattr(CloudType, cloud.upper())
            except AttributeError:
                raise TypeError(
                    "Wrong type specified, valid types are: worx, landxcape or kress"
                )

        self._cloud = cloud

        # Get token from AUTH endpoint
        self.token = Token(self._email, self._password, self._cloud)

        if isinstance(self.token.access_token, type(None)) or isinstance(
            self.token.refresh_token, type(None)
        ):
            raise TokenError("Access or refresh token was not found")

        # Get all available mowers and convert them to a list of serial numbers
        self.mowers = GET(
            f"https://{self._cloud.ENDPOINT}/api/v2/product-items?status=1",
            HEADERS(self.token.access_token),
        )

        for mower in self.mowers:
            mower.update({"has_data": False})

        mqtt_endpoint = self.mowers[0]["mqtt_endpoint"]
        user_id = self.mowers[0]["user_id"]

        # Initialize the MQTT connector
        self.mqtt = MQTT(
            self.token.access_token,
            self._cloud.BRAND_PREFIX,
            mqtt_endpoint,
            user_id,
            self.on_update,
        )

    def get_mower(self, serial_number: str) -> dict:
        """Get a specific mower."""
        for mower in self.mowers:
            if mower["serial_number"] == serial_number:
                return mower

        raise MowerNotFoundError(
            f"Mower with serialnumber {serial_number} was not found."
        )

    def connect(self) -> None:
        """Connect to MQTT and subscribe to updates."""
        for mower in self.mowers:
            self.mqtt.subscribe(mower["mqtt_topics"]["command_out"])

        self.mqtt.connect()

    def disconnect(self) -> None:
        """Disconnect from MQTT."""
        self.mqtt.disconnect()

    def update(self, serial_number) -> None:
        """Request a state refresh."""
        mower = self.get_mower(serial_number)
        self.mqtt.ping(serial_number, mower["mqtt_topics"]["command_in"])

    def write_data(self, serial_number: str, data: str) -> None:
        """Update mower data."""
        for mower in self.mowers:
            if mower["serial_number"] == serial_number:
                mower.update(data)
                mower.update({"has_data": True})
                break

    def on_update(self, topic, payload, dup, qos, retain, **kwargs):
        """Triggered when a MQTT message was received."""
        data = json.loads(payload)
        # sn = payload["cfg"]["sn"]
        # print(
        #     "Received message from {} on topic '{}': {}".format(
        #         data["cfg"]["sn"], topic, payload
        #     )
        # )
        self.write_data(data["cfg"]["sn"], data)
