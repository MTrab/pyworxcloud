"""MQTT information class."""
from __future__ import annotations

import json
import logging
import random
import time
import urllib.parse
from datetime import datetime
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from awsiot import mqtt, mqtt_connection_builder

from ..events import EventHandler
from .landroid_class import LDict

_LOGGER = logging.getLogger(__name__)


class MQTTMsgType(LDict):
    """Define specific message type data."""

    def __init__(self) -> dict:
        super().__init__()

        self["in"] = 0
        self["out"] = 0


class MQTTMessageItem(LDict):
    """Defines a MQTT message for Landroid Cloud."""

    def __init__(
        self, device: str, data: str = "{}", qos: int = 0, retain: bool = False
    ) -> dict:
        super().__init__()

        self["device"] = device
        self["data"] = data
        self["qos"] = qos
        self["retain"] = retain


class MQTTMessages(LDict):
    """Messages class."""

    def __init__(self) -> dict:
        super().__init__()

        self["raw"] = MQTTMsgType()
        self["filtered"] = MQTTMsgType()


class MQTTTopics(LDict):
    """Topics class."""

    def __init__(
        self, topic_in: str | None = None, topic_out: str | None = None
    ) -> dict:
        super().__init__()

        self["in"] = topic_in
        self["out"] = topic_out


class Command:
    """Landroid Cloud commands."""

    FORCE_REFRESH = 0
    START = 1
    PAUSE = 2
    HOME = 3
    ZONETRAINING = 4
    LOCK = 5
    UNLOCK = 6
    RESTART = 7
    PAUSE_OVER_WIRE = 8
    SAFEHOME = 9


class MQTT(LDict):
    """Full MQTT handler class."""

    def __init__(
        self,
        token: str,
        brandprefix: str,
        endpoint: str,
        user_id: int,
        callback: Any,
    ) -> dict:
        """Initialize AWSIoT MQTT handler."""
        super().__init__()
        self.client = None
        self._events = EventHandler()
        self._on_update = callback

        accesstokenparts = token.replace("_", "/").replace("-", "+").split(".")

        self._uuid = uuid4()

        self._configuration = mqtt_connection_builder.direct_with_custom_authorizer(
            endpoint=endpoint,
            auth_username=f"bot?jwt={urllib.parse.quote(accesstokenparts[0])}.{urllib.parse.quote(accesstokenparts[1])}",
            auth_authorizer_name="",
            auth_authorizer_signature=urllib.parse.quote(accesstokenparts[2]),
            auth_password=None,
            port=443,
            client_id=f"{brandprefix}/USER/{user_id}/bot/{self._uuid}",
            clean_session=False,
        )

    def subscribe(self, topic: str) -> None:
        """Subscribe to MQTT updates."""
        self._configuration.subscribe(
            topic=topic,
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=self._on_update,
        )

    def connect(self) -> None:
        """Connect to the MQTT service."""
        connect_future = self._configuration.connect()
        self.client = connect_future.result()

    def disconnect(
        self, reasoncode=None, properties=None  # pylint: disable=unused-argument
    ):
        """Disconnect from AWSIoT MQTT server."""
        self.client = None
        self._configuration.disconnect()

    def ping(self, serial_number: str, topic: str) -> None:
        """Ping (update) the mower."""
        cmd = self.format_message(serial_number, {"cmd": Command.FORCE_REFRESH})
        _LOGGER.debug("Sending '%s' on topic '%s'", cmd, topic)
        self._configuration.publish(topic, cmd, mqtt.QoS.AT_LEAST_ONCE)

    def command(self, serial_number: str, topic: str, action: Command) -> None:
        """Send a specific command to the mower."""
        cmd = self.format_message(serial_number, {"cmd": action})
        _LOGGER.debug("Sending '%s' on topic '%s'", cmd, topic)
        self._configuration.publish(topic, cmd, mqtt.QoS.AT_LEAST_ONCE)

    def publish(self, serial_number: str, topic: str, message: dict) -> None:
        """Publish message to the mower."""
        _LOGGER.debug("Publishing message '%s'", message)
        self._configuration.publish(
            topic,
            self.format_message(serial_number, message),
            mqtt.QoS.AT_LEAST_ONCE,
        )

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
        _LOGGER.debug("Formatting message '%s' to '%s'", message, msg)

        return json.dumps(msg)
