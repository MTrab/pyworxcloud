"""MQTT information class.

This module provides an MQTT client for connecting to AWS IoT MQTT using the AWS IoT Device SDK for Python v2.
It handles connection, subscription, and message publishing to AWS IoT MQTT endpoints.

Dependencies:
- awscrt: AWS Common Runtime library
- awsiot: AWS IoT Device SDK for Python v2

The MQTT class provides the following functionality:
- Connection to AWS IoT MQTT with custom authentication using JWT tokens
- Subscription to topics
- Publishing messages to topics
- Handling reconnection and token updates
- Formatting messages for different protocols
"""

from __future__ import annotations

import json
import random
import threading
import urllib.parse
from concurrent.futures import Future
from datetime import datetime
from logging import Logger
from typing import Any, Optional
from uuid import uuid4

import awscrt.io
import awscrt.mqtt
from awsiot import mqtt_connection_builder

from ..events import EventHandler, LandroidEvent
from ..exceptions import NoConnectionError, TimeoutException
from .landroid_class import LDict

QOS_FLAG = awscrt.mqtt.QoS.AT_LEAST_ONCE
DEFAULT_RESPONSE_TIMEOUT = 30.0


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
        self._events = EventHandler()
        self._on_update = callback
        self._endpoint = endpoint
        self._log = logger.getChild("MQTT")
        self._reconnected: bool = False
        self._topic: list = []
        self._api = api
        self._uuid = uuid4()
        self._is_connected: bool = False
        self._brandprefix = brandprefix
        self._user_id = user_id
        self._connection_future: Optional[Future] = None
        self._command_lock = threading.Lock()
        self._response_lock = threading.Lock()
        self._response_event = threading.Event()
        self._pending_response_target: str | None = None
        self._pending_response_message_id: int | None = None
        self._client_id = (
            f"{self._brandprefix}/USER/{self._user_id}/homeassistant/{self._uuid}"
        )

        # Create event loop group and connection
        self._event_loop_group = awscrt.io.EventLoopGroup(1)
        self._host_resolver = awscrt.io.DefaultHostResolver(self._event_loop_group)
        self._client_bootstrap = awscrt.io.ClientBootstrap(
            self._event_loop_group, self._host_resolver
        )

        # Create the MQTT connection
        self.client = self._create_mqtt_connection()

    def _create_mqtt_connection(self):
        """Create an MQTT connection using awsiot.mqtt_connection_builder."""
        # Format the JWT token for authentication
        accesstokenparts = (
            self._api.access_token.replace("_", "/").replace("-", "+").split(".")
        )
        username = f"bot?jwt={urllib.parse.quote(accesstokenparts[0])}.{urllib.parse.quote(accesstokenparts[1])}&x-amz-customauthorizer-name=''&x-amz-customauthorizer-signature={urllib.parse.quote(accesstokenparts[2])}"

        # Create the MQTT connection
        mqtt_connection = mqtt_connection_builder.websockets_with_custom_authorizer(
            endpoint=self._endpoint,
            client_id=self._client_id,
            auth_username=username,
            auth_password=None,
            client_bootstrap=self._client_bootstrap,
            on_connection_interrupted=self._on_connection_interrupted,
            on_connection_resumed=self._on_connection_resumed,
            clean_session=False,
            keep_alive_secs=30,
        )

        return mqtt_connection

    def _on_connection_interrupted(self, connection, error, **kwargs):
        """Callback when a connection is accidentally lost."""
        logger = self._log.getChild("Conn_State")
        self._is_connected = False
        logger.debug(f"Connection interrupted. error: {error}")
        self._events.call(LandroidEvent.MQTT_CONNECTION, state=False)

    def _on_connection_resumed(
        self, connection, return_code, session_present, **kwargs
    ):
        """Callback when an interrupted connection is re-established."""
        logger = self._log.getChild("Conn_State")
        self._is_connected = True
        logger.debug(
            f"Connection resumed. return_code: {return_code}, session_present: {session_present}"
        )

        if (
            return_code == awscrt.mqtt.ConnectReturnCode.ACCEPTED
            and not session_present
        ):
            logger.debug("Session did not persist. Resubscribing to existing topics...")
            for topic in self._topic:
                logger.debug(f"Resubscribing to '{topic}'")
                self.subscribe(topic, False)

        self._events.call(LandroidEvent.MQTT_CONNECTION, state=True)

    @property
    def connected(self) -> bool:
        """Returns the MQTT connection state."""
        return self._is_connected
        # return self.client.is_connected()

    def _on_message_received(self, topic: str, payload: bytes, **kwargs) -> None:
        """Callback when a message is received."""
        msg = payload.decode("utf-8")
        self._log.debug("Received MQTT message on topic '%s':\n%s", topic, msg)
        identifiers, message_ids = self._extract_response_markers(msg)
        with self._response_lock:
            id_matches = (
                not message_ids
                or self._pending_response_message_id is None
                or self._pending_response_message_id in message_ids
            )
            if (
                self._pending_response_target is not None
                and self._pending_response_target in identifiers
                and id_matches
            ):
                self._response_event.set()
        self._on_update(msg)

    def _extract_response_markers(self, payload: str) -> tuple[set[str], set[int]]:
        """Extract identifiers and command ids from an incoming MQTT payload."""
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return set(), set()

        identifiers: set[str] = set()
        message_ids: set[int] = set()
        cfg = data["cfg"] if isinstance(data, dict) and "cfg" in data else {}
        dat = data["dat"] if isinstance(data, dict) and "dat" in data else {}

        if isinstance(cfg, dict) and "sn" in cfg and cfg["sn"] is not None:
            identifiers.add(str(cfg["sn"]))
        if isinstance(cfg, dict) and "id" in cfg and isinstance(cfg["id"], int):
            message_ids.add(cfg["id"])

        if isinstance(dat, dict):
            if "uuid" in dat and dat["uuid"] is not None:
                identifiers.add(str(dat["uuid"]))
            if "mac" in dat and dat["mac"] is not None:
                identifiers.add(str(dat["mac"]))
            if "id" in dat and isinstance(dat["id"], int):
                message_ids.add(dat["id"])

        if isinstance(data, dict) and "id" in data and isinstance(data["id"], int):
            message_ids.add(data["id"])

        return identifiers, message_ids

    def subscribe(self, topic: str, append: bool = True) -> None:
        """Subscribe to MQTT updates."""
        if append and topic not in self._topic:
            self._topic.append(topic)

        subscribe_future, _ = self.client.subscribe(
            topic=topic, qos=QOS_FLAG, callback=self._on_message_received
        )

        # Wait for a subscription to be confirmed
        subscribe_future.result()
        self._log.debug(f"Subscribed to topic: {topic}")

    def connect(self) -> None:
        """Connect to the MQTT service."""
        try:
            # Create a connection future
            self._connection_future = self.client.connect()

            # Wait for connection to complete
            connect_result = self._connection_future.result()
            self._log.debug(f"Connected with result: {connect_result}")

            # Update connection state
            self._is_connected = True
            self._reconnected = False

            # Subscribe to saved topics
            for topic in self._topic:
                self._log.debug(f"Subscribing to '{topic}'")
                self.subscribe(topic, False)

            # Notify about connection
            self._events.call(LandroidEvent.MQTT_CONNECTION, state=True)

        except Exception as exc:
            self._is_connected = False
            self._log.error(f"Failed to connect to MQTT: {exc}")
            raise NoConnectionError() from exc

    def update_token(self) -> None:
        """Update the token."""
        self._log.debug("Updating token")

        # Disconnect if connected
        if self.connected:
            self.disconnect(keep_topic=True)

        # Create a new connection with updated token
        self.client = self._create_mqtt_connection()

        # Reconnect
        self.connect()

        self._log.debug("Token updated")

    def disconnect(self, keep_topic: bool = False):  # pylint: disable=unused-argument
        """Disconnect from AWSIoT MQTT server."""
        logger = self._log.getChild("MQTT_Disconnect")

        if self.connected:
            # Clear topic list
            if not keep_topic:
                self._topic = []

            # Disconnect
            disconnect_future = self.client.disconnect()
            disconnect_future.result()

            # Update state
            self._is_connected = False
            logger.debug("MQTT disconnected")

    def ping(self, serial_number: str, topic: str, protocol: int = 0) -> None:
        """Ping (update) the mower."""
        cmd = {"cmd": Command.FORCE_REFRESH}
        self._log.debug("Sending '%s' on topic '%s'", cmd, topic)
        self.publish(serial_number, topic, cmd, protocol)

    def command(
        self,
        serial_number: str,
        topic: str,
        action: Command,
        protocol: int = 0,
        timeout: float = DEFAULT_RESPONSE_TIMEOUT,
    ) -> None:
        """Send a specific command to the mower."""
        self.publish(
            serial_number=serial_number,
            topic=topic,
            message={"cmd": action},
            protocol=protocol,
            timeout=timeout,
        )

    def publish(
        self,
        serial_number: str,
        topic: str,
        message: dict,
        protocol: int = 0,
        timeout: float = DEFAULT_RESPONSE_TIMEOUT,
    ) -> None:
        """Publish a message to the mower and wait for response."""
        if not self.connected:
            self.update_token()

        # Format the message
        formatted_message = self.format_message(serial_number, message, protocol)
        command_message_id = json.loads(formatted_message)["id"]
        self._log.debug("Publishing message '%s'", formatted_message)

        # Only allow one in-flight command until response/timeout.
        with self._command_lock:
            with self._response_lock:
                self._pending_response_target = serial_number
                self._pending_response_message_id = command_message_id
                self._response_event.clear()

            try:
                # Publish the message
                publish_future, _ = self.client.publish(
                    topic=topic, payload=formatted_message, qos=QOS_FLAG
                )

                # Wait for the message to be published
                publish_future.result()

                if not self._response_event.wait(timeout):
                    raise TimeoutException(
                        f"Timed out waiting for device response from '{serial_number}'"
                    )
            finally:
                with self._response_lock:
                    self._pending_response_target = None
                    self._pending_response_message_id = None
                    self._response_event.clear()

    def format_message(self, serial_number: str, message: dict, protocol: int) -> str:
        """
        Format a message.
        Message is expected to be a dict like this: {"cmd": 1}
        """
        now = datetime.now()
        msg = {}
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
