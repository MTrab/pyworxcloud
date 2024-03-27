"""MQTT information class."""

from __future__ import annotations

import asyncio
import json
import random
import ssl
import urllib.parse
from datetime import datetime
from logging import Logger
from typing import Any
from uuid import uuid4

import paho.mqtt.client as mqtt
from paho.mqtt.client import connack_string

from ..events import EventHandler, LandroidEvent
from .landroid_class import LDict

QOS_FLAG = 1


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
        api: Any,
        brandprefix: str,
        endpoint: str,
        user_id: int,
        logger: Logger,
        callback: Any,
    ) -> dict:
        """Initialize AWSIoT MQTT handler."""
        super().__init__()
        # self.client = None
        self._events = EventHandler()
        self._on_update = callback
        self._endpoint = endpoint
        self._log = logger.getChild("MQTT")
        self._disconnected = False
        self._topic: list = []
        self._api = api

        self._uuid = uuid4()

        self.client = mqtt.Client(
            client_id=f"{brandprefix}/USER/{user_id}/bot/{self._uuid}",
            clean_session=False,
            userdata=None,
            reconnect_on_failure=True,
        )

        accesstokenparts = (
            api.access_token.replace("_", "/").replace("-", "+").split(".")
        )
        self.client.username_pw_set(
            username=f"bot?jwt={urllib.parse.quote(accesstokenparts[0])}.{urllib.parse.quote(accesstokenparts[1])}&x-amz-customauthorizer-name=''&x-amz-customauthorizer-signature={urllib.parse.quote(accesstokenparts[2])}",  # pylint: disable= line-too-long
            password=None,
        )

        ssl_context = ssl.create_default_context()
        ssl_context.set_alpn_protocols(["mqtt"])
        self.client.tls_set_context(context=ssl_context)
        self.client.reconnect_delay_set(min_delay=10, max_delay=300)

        self.client.on_connect = self._on_connect
        self.client.on_message = self._forward_on_message
        self.client.on_disconnect = self._on_disconnect

    @property
    def connected(self) -> bool:
        """Returns the MQTT connection state."""
        return self.client.is_connected()

    def _forward_on_message(
        self,
        client: mqtt.Client | None,  # pylint: disable=unused-argument
        userdata: Any | None,  # pylint: disable=unused-argument
        message: Any | None,
        properties: Any | None = None,  # pylint: disable=unused-argument
    ) -> None:
        """MQTT callback method definition."""
        msg = message.payload.decode("utf-8")
        self._log.debug("Received MQTT message:\n%s", msg)
        self._on_update(msg)

    def subscribe(self, topic: str, append: bool = True) -> None:
        """Subscribe to MQTT updates."""
        if append and topic not in self._topic:
            self._topic.append(topic)
        self.client.subscribe(topic=topic, qos=QOS_FLAG)

    def connect(self) -> None:
        """Connect to the MQTT service."""
        self.client.connect(self._endpoint, 443, 45)
        self.client.loop_start()

    def _on_connect(
        self,
        client: mqtt.Client | None,  # pylint: disable=unused-argument
        userdata: Any | None,  # pylint: disable=unused-argument
        flags: Any | None,  # pylint: disable=unused-argument
        rc: int | None,
        properties: Any | None = None,  # pylint: disable=unused-argument,invalid-name
    ) -> None:
        """MQTT callback method."""
        logger = self._log.getChild("Conn_State")
        logger.debug(connack_string(rc))
        if rc == 0:
            self._disconnected = False
            logger.debug("MQTT connected")
            self._events.call(
                LandroidEvent.MQTT_CONNECTION, state=self.client.is_connected()
            )
            for topic in self._topic:
                self.subscribe(topic, False)
        else:
            logger.debug("MQTT connection failed")
            self._events.call(
                LandroidEvent.MQTT_CONNECTION, state=self.client.is_connected()
            )

    def _on_disconnect(
        self,
        client: mqtt.Client | None,  # pylint: disable=unused-argument
        userdata: Any | None,  # pylint: disable=unused-argument
        rc: int | None,
        properties: Any | None = None,  # pylint: disable=unused-argument,invalid-name
    ) -> None:
        """MQTT callback method."""
        logger = self._log.getChild("Conn_State")
        if rc > 0:
            if rc == 7:
                logger.debug("Refreshing access token and reconnecting")
                self._api.update_token()
                accesstokenparts = (
                    self._api.access_token.replace("_", "/")
                    .replace("-", "+")
                    .split(".")
                )
                self.client.username_pw_set(
                    username=f"bot?jwt={urllib.parse.quote(accesstokenparts[0])}.{urllib.parse.quote(accesstokenparts[1])}&x-amz-customauthorizer-name=''&x-amz-customauthorizer-signature={urllib.parse.quote(accesstokenparts[2])}",  # pylint: disable= line-too-long
                    password=None,
                )
                self.connect()
            else:
                logger.debug(
                    "Unexpected MQTT disconnect (%s: %s) - retrying",
                    rc,
                    connack_string(rc),
                )
                try:
                    self.client.reconnect()
                except:  # pylint: disable=bare-except
                    pass

    def disconnect(
        self, reasoncode=None, properties=None  # pylint: disable=unused-argument
    ):
        """Disconnect from AWSIoT MQTT server."""
        logger = self._log.getChild("MQTT_Disconnect")
        for topic in self._topic:
            logger.debug("Unsubscribing '%s'", topic)
            self.client.unsubscribe(topic)
        self._topic = []
        self._disconnected = True
        self.client.loop_stop()
        self.client.disconnect()

    def ping(self, serial_number: str, topic: str, protocol: int = 0) -> None:
        """Ping (update) the mower."""
        cmd = self.format_message(
            serial_number, {"cmd": Command.FORCE_REFRESH}, protocol
        )
        self._log.debug("Sending '%s' on topic '%s'", cmd, topic)
        self.client.publish(topic, cmd, QOS_FLAG)

    def command(
        self, serial_number: str, topic: str, action: Command, protocol: int = 0
    ) -> None:
        """Send a specific command to the mower."""
        cmd = self.format_message(serial_number, {"cmd": action}, protocol)
        self._log.debug("Sending '%s' on topic '%s'", cmd, topic)
        self.client.publish(topic, cmd, QOS_FLAG)

    def publish(
        self, serial_number: str, topic: str, message: dict, protocol: int = 0
    ) -> None:
        """Publish message to the mower."""
        if not self.connected:
            self._log.warning("Not connected to API endpoint - awaiting connection")
            asyncio.sleep(15)
            self.connect()
            # Call publish rather than continue to handle connection issues
            self.publish(serial_number, topic, message)
        else:
            self._log.debug("Publishing message '%s'", message)
            self.client.publish(
                topic, self.format_message(serial_number, message, protocol), QOS_FLAG
            )

    def format_message(self, serial_number: str, message: dict, protocol: int) -> str:
        """
        Format a message.
        Message is expected to be a dict like this: {"cmd": 1}
        """
        now = datetime.now()
        if protocol == 0:
            msg = {
                "id": random.randint(1024, 65535),
                "sn": serial_number,
                "tm": now.strftime("%H:%M:%S"),
                "dt": now.strftime("%d/%m/%Y"),
            }
        elif protocol == 1:
            msg = {
                "id": random.randint(1024, 65535),
                "uuid": serial_number,
                "tm": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }

        msg.update(message)
        self._log.debug("Formatting message '%s' to '%s'", message, msg)

        return json.dumps(msg)
