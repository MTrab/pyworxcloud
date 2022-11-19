"""MQTT handler."""
from __future__ import annotations

import json
import pathlib
import random
import urllib.parse
from datetime import datetime
from uuid import uuid4

from awsiot import mqtt, mqtt_connection_builder

from ..commands import WorxCommand


class MQTT:
    """Class of MQTT commands."""

    def __init__(
        self, token: str, brandprefix: str, endpoint: str, user_id: int, callback
    ) -> None:
        """Initialize the MQTT handler."""
        self.client = None
        self.callback = callback

        accessTokenParts = token.replace("_", "/").replace("-", "+").split(".")

        self._uuid = uuid4()

        cwd = pathlib.Path(__file__).parent.resolve()
        cert = f"{cwd}/../cert/AmazonRootCA1.pem"

        self._configuration = mqtt_connection_builder.direct_with_custom_authorizer(
            endpoint=endpoint,
            ca_filepath=cert,
            auth_username=f"bot?jwt={urllib.parse.quote(accessTokenParts[0])}.{urllib.parse.quote(accessTokenParts[1])}",
            auth_authorizer_name="",
            auth_authorizer_signature=urllib.parse.quote(accessTokenParts[2]),
            auth_password=None,
            port=443,
            client_id=f"{brandprefix}/USER/{user_id}/bot/{self._uuid}",
            clean_session=False,
        )

    def subscribe(self, topic: str) -> None:
        """Subscribe to MQTT updates."""
        # self._configuration.subscribe(
        #     topic=topic,
        #     qos=mqtt.QoS.AT_LEAST_ONCE,
        #     callback=self.callback,
        # )

    def connect(self) -> None:
        """Connect to the MQTT service."""
        connect_future = self._configuration.connect()
        self.client = connect_future.result()

    def disconnect(self) -> None:
        """Disconnect from MQTT server."""
        self.client = None
        self._configuration.disconnect()

    def ping(self, serial_number: str, topic: str) -> None:
        """Ping (update) the mower."""
        now = datetime.now()
        message = {
            "id": random.randint(1024, 65535),
            "cmd": 0,
            "sn": serial_number,
            "tm": now.strftime("%H:%M:%S"),
            "dt": now.strftime("%d/%m/%Y"),
        }

        self._configuration.publish(topic, json.dumps(message), mqtt.QoS.AT_LEAST_ONCE)

    def publish(self, serial_number: str, topic: str, message: str) -> None:
        """Publish message to the mower."""
        self._configuration.publish(topic, json.dumps(message), mqtt.QoS.AT_LEAST_ONCE)

    def format_message(self, serial_number: str, message: dict) -> str:
        """
        Format a message.
        Message is expected to be a dict like this: {"cmd": 1}
        """
        now = datetime.now()
        msg = {
            "id": random.randint(1024, 65535),
            "sn": serial_number,
            "tm": now.strftime("%H:%M:%S"),
            "dt": now.strftime("%d/%m/%Y"),
        }
        msg.update(message)
        return msg
