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

import asyncio
import itertools
import json
import random
import threading
import time
import urllib.parse
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime, timezone
from logging import Logger
from typing import Any, Callable, Optional
from uuid import uuid4

import awscrt.io
import awscrt.mqtt
from awsiot import mqtt_connection_builder

from ..events import EventHandler, LandroidEvent
from ..exceptions import NoConnectionError, TimeoutException
from .landroid_class import LDict

QOS_FLAG = awscrt.mqtt.QoS.AT_LEAST_ONCE
DEFAULT_RESPONSE_TIMEOUT = 30.0
DEFAULT_DISCONNECT_TIMEOUT = 0.5
DEFAULT_SHUTDOWN_TIMEOUT = 0.25


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
        identifier_resolver: Callable[[str], set[str]] | None = None,
        deduplicate_inflight_commands: bool = False,
        response_timeout: float = DEFAULT_RESPONSE_TIMEOUT,
    ) -> dict:
        """Initialize AWSIoT MQTT handler."""

        super().__init__()
        self._events = EventHandler()
        self._on_update = callback
        self._identifier_resolver = identifier_resolver
        self._deduplicate_inflight_commands = deduplicate_inflight_commands
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
        self._pending_command_signature: tuple[str, str, int, str] | None = None
        self._last_command_payload: dict[str, Any] | None = None
        self._lifecycle_lock = threading.RLock()
        self._token_update_lock = threading.Lock()
        self._ready_event = threading.Event()
        self._message_id_lock = threading.Lock()
        self._message_id_seq = itertools.count(random.randint(1024, 65535))
        self._client_generation = 0
        self._active_generation = 0
        if response_timeout <= 0:
            raise ValueError("response_timeout must be greater than 0")
        self._response_timeout = float(response_timeout)
        self._client_id = (
            f"{self._brandprefix}/USER/{self._user_id}/homeassistant/{self._uuid}"
        )
        self._shutdown_event = False
        self._disconnect_timeout = DEFAULT_DISCONNECT_TIMEOUT
        self._shutdown_timeout = DEFAULT_SHUTDOWN_TIMEOUT

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
        generation = self._client_generation + 1
        self._client_generation = generation
        self._active_generation = generation

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
            on_connection_interrupted=lambda connection, error, **kwargs: self._on_connection_interrupted(
                connection, error, generation=generation, **kwargs
            ),
            on_connection_resumed=lambda connection, return_code, session_present, **kwargs: self._on_connection_resumed(
                connection,
                return_code,
                session_present,
                generation=generation,
                **kwargs,
            ),
            clean_session=False,
            keep_alive_secs=30,
        )

        return mqtt_connection

    def _is_stale_generation(self, generation: int | None) -> bool:
        """Return whether a callback generation no longer matches the active client."""
        if generation is None:
            return False
        with self._lifecycle_lock:
            return generation != self._active_generation

    def _get_ready_event(self) -> threading.Event:
        """Return the readiness event, creating it for bare test fixtures if needed."""
        ready_event = getattr(self, "_ready_event", None)
        if ready_event is None:
            ready_event = threading.Event()
            self._ready_event = ready_event
            if getattr(self, "_is_connected", False):
                ready_event.set()
        return ready_event

    def _resubscribe_topic(self, topic: str, generation: int | None = None) -> None:
        """Resubscribe while tolerating older monkeypatched subscribe signatures."""
        try:
            self.subscribe(topic, False, generation=generation)
        except TypeError as err:
            if "generation" not in str(err):
                raise
            self.subscribe(topic, False)

    def _on_connection_interrupted(self, connection, error, **kwargs):
        """Callback when a connection is accidentally lost."""
        del connection
        logger = self._log.getChild("Conn_State")
        generation = kwargs.get("generation")
        if self._is_stale_generation(generation):
            logger.debug(
                "Ignoring stale connection interrupted callback for generation %s",
                generation,
            )
            return

        self._is_connected = False
        self._get_ready_event().clear()
        logger.debug(f"Connection interrupted. error: {error}")
        self._events.call(LandroidEvent.MQTT_CONNECTION, state=False)

    def _on_connection_resumed(
        self, connection, return_code, session_present, **kwargs
    ):
        """Callback when an interrupted connection is re-established."""
        del connection
        logger = self._log.getChild("Conn_State")
        generation = kwargs.get("generation")
        if self._is_stale_generation(generation):
            logger.debug(
                "Ignoring stale connection resumed callback for generation %s",
                generation,
            )
            return

        self._is_connected = True
        logger.debug(
            f"Connection resumed. return_code: {return_code}, session_present: {session_present}"
        )

        if return_code == awscrt.mqtt.ConnectReturnCode.ACCEPTED:
            if session_present:
                logger.debug(
                    "Session resumed. Resubscribing to existing topics defensively..."
                )
            else:
                logger.debug(
                    "Session did not persist. Resubscribing to existing topics..."
                )
            for topic in self._topic:
                logger.debug(f"Resubscribing to '{topic}'")
                self._resubscribe_topic(topic, generation)

        self._get_ready_event().set()
        self._events.call(LandroidEvent.MQTT_CONNECTION, state=True)

    @property
    def connected(self) -> bool:
        """Returns the MQTT connection state."""
        return self._is_connected
        # return self.client.is_connected()

    def _on_message_received(
        self, topic: str, payload: bytes, generation: int | None = None, **kwargs
    ) -> None:
        """Callback when a message is received."""
        del kwargs
        if self._is_stale_generation(generation):
            self._log.debug(
                "Ignoring stale MQTT message callback for generation %s", generation
            )
            return

        msg = payload.decode("utf-8")
        self._log.debug("Received MQTT message on topic '%s':\n%s", topic, msg)
        identifiers, message_ids = self._extract_response_markers(msg)
        expanded_identifiers = self._expand_identifiers(identifiers)
        with self._response_lock:
            id_matches = (
                not message_ids
                or self._pending_response_message_id is None
                or self._pending_response_message_id in message_ids
            )
            if (
                self._pending_response_target is not None
                and self._pending_response_target in expanded_identifiers
                and id_matches
            ):
                self._response_event.set()
        self._on_update(msg)

    def _expand_identifiers(self, identifiers: set[str]) -> set[str]:
        """Expand identifiers using optional mower alias resolver."""
        expanded = set(identifiers)
        resolver = self._identifier_resolver
        if resolver is None:
            return expanded

        for identifier in list(identifiers):
            try:
                aliases = resolver(identifier)
            except Exception:  # pragma: no cover - defensive resolver guard
                aliases = set()
            if aliases:
                expanded.update(str(alias) for alias in aliases if alias is not None)
        return expanded

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

    def subscribe(
        self, topic: str, append: bool = True, generation: int | None = None
    ) -> None:
        """Subscribe to MQTT updates."""
        if append and topic not in self._topic:
            self._topic.append(topic)

        client = self.client
        if client is None:
            raise NoConnectionError("MQTT client is not available")

        callback_generation = (
            self._active_generation if generation is None else generation
        )
        subscribe_future, _ = client.subscribe(
            topic=topic,
            qos=QOS_FLAG,
            callback=lambda topic, payload, **kwargs: self._on_message_received(
                topic, payload, generation=callback_generation, **kwargs
            ),
        )

        # Wait for a subscription to be confirmed
        subscribe_future.result()
        self._log.debug(f"Subscribed to topic: {topic}")

    async def asubscribe(
        self, topic: str, append: bool = True, generation: int | None = None
    ) -> None:
        """Async subscribe wrapper."""
        await asyncio.to_thread(self.subscribe, topic, append, generation)

    def connect(self) -> None:
        """Connect to the MQTT service."""
        with self._lifecycle_lock:
            client = self.client
            generation = self._active_generation
        if client is None:
            raise NoConnectionError("MQTT client is not available")

        self._get_ready_event().clear()
        try:
            # Create a connection future
            self._connection_future = client.connect()

            # Wait for connection to complete
            self._connection_future.result()

            with self._lifecycle_lock:
                if generation != self._active_generation or client is not self.client:
                    self._log.debug(
                        "Ignoring late connect completion for stale generation %s",
                        generation,
                    )
                    return

                # Update connection state
                self._is_connected = True
                self._reconnected = False

            # Subscribe to saved topics
            for topic in self._topic:
                self._log.debug(f"Subscribing to '{topic}'")
                self._resubscribe_topic(topic, generation)

            # Notify about connection
            self._get_ready_event().set()
            self._events.call(LandroidEvent.MQTT_CONNECTION, state=True)

        except Exception as exc:
            self._is_connected = False
            self._connection_future = None
            self._get_ready_event().clear()
            self._log.error(f"Failed to connect to MQTT: {exc}")
            raise NoConnectionError() from exc

    async def aconnect(self) -> None:
        """Async connect wrapper."""
        await asyncio.to_thread(self.connect)

    def update_token(self) -> None:
        """Update the token."""
        if not self._token_update_lock.acquire(blocking=False):
            self._log.debug("Token update already in progress; waiting for MQTT ready")
            self._wait_until_ready(self._response_timeout)
            return

        try:
            with self._command_lock:
                self._log.debug("Updating token")
                self._get_ready_event().clear()

                # Disconnect if connected
                if self.connected:
                    self.disconnect(keep_topic=True)

                # Create a new connection with updated token
                self.client = self._create_mqtt_connection()

                # Reconnect
                self.connect()

                self._log.debug("Token updated")
        finally:
            self._token_update_lock.release()

    async def aupdate_token(self) -> None:
        """Async token update wrapper."""
        await asyncio.to_thread(self.update_token)

    def disconnect(self, keep_topic: bool = False):  # pylint: disable=unused-argument
        """Disconnect from AWSIoT MQTT server."""
        logger = self._log.getChild("MQTT_Disconnect")
        with self._lifecycle_lock:
            if self._shutdown_event:
                self._is_connected = False
                self._connection_future = None
                self._get_ready_event().clear()
                return

            # Clear topic list
            if not keep_topic:
                self._topic = []

            client = self.client
            if client is None:
                self._is_connected = False
                self._get_ready_event().clear()
                return

            try:
                if self._is_connected:
                    started = time.perf_counter()
                    disconnect_future = client.disconnect()
                    disconnect_future.result(
                        timeout=getattr(
                            self,
                            "_disconnect_timeout",
                            DEFAULT_DISCONNECT_TIMEOUT,
                        )
                    )
                    logger.debug(
                        "MQTT disconnected in %.3fs", time.perf_counter() - started
                    )
            except FutureTimeoutError:  # pragma: no cover - defensive
                logger.debug(
                    "MQTT disconnect timed out after %.3fs",
                    time.perf_counter() - started,
                )
            except Exception as err:  # pragma: no cover - defensive
                logger.debug("MQTT disconnect raised during teardown: %s", err)
            finally:
                # Ensure internal state remains consistent after teardown attempts.
                self._is_connected = False
                self._connection_future = None
                self._get_ready_event().clear()

    async def adisconnect(self, keep_topic: bool = False) -> None:
        """Async disconnect wrapper."""
        await asyncio.to_thread(self.disconnect, keep_topic)

    def shutdown(self) -> None:
        """Release background AWS CRT resources."""
        logger = self._log.getChild("MQTT_Shutdown")
        with self._lifecycle_lock:
            if self._shutdown_event:
                return
            self._shutdown_event = True
            was_connected = self._is_connected

            host_resolver = self._host_resolver
            client_bootstrap = self._client_bootstrap
            event_loop_group = self._event_loop_group
            client = self.client

            self.client = None
            self._host_resolver = None
            self._client_bootstrap = None
            self._event_loop_group = None
            self._is_connected = False
            self._connection_future = None
            self._get_ready_event().clear()

        # Disconnect after detaching internals, so concurrent calls see teardown state.
        if client is not None and was_connected:
            try:
                started = time.perf_counter()
                disconnect_future = client.disconnect()
                disconnect_future.result(
                    timeout=getattr(self, "_shutdown_timeout", DEFAULT_SHUTDOWN_TIMEOUT)
                )
                logger.debug(
                    "Shutdown disconnect completed in %.3fs",
                    time.perf_counter() - started,
                )
            except FutureTimeoutError:  # pragma: no cover - defensive
                logger.debug(
                    "Shutdown disconnect timed out after %.3fs",
                    time.perf_counter() - started,
                )
            except Exception:  # pragma: no cover - defensive
                logger.debug(
                    "Shutdown disconnect raised after %.3fs",
                    time.perf_counter() - started,
                    exc_info=True,
                )
        shutdown_timeout = getattr(self, "_shutdown_timeout", DEFAULT_SHUTDOWN_TIMEOUT)
        for name, resource in (
            ("host_resolver", host_resolver),
            ("client_bootstrap", client_bootstrap),
            ("event_loop_group", event_loop_group),
        ):
            if resource is None:
                continue

            shutdown_event = getattr(resource, "shutdown_event", None)
            if shutdown_event is None:
                logger.debug("Detached %s without shutdown_event", name)
                continue

            started = time.perf_counter()
            completed = shutdown_event.wait(shutdown_timeout)
            logger.debug(
                "Waited for %s shutdown_event; completed=%s in %.3fs",
                name,
                completed,
                time.perf_counter() - started,
            )

    async def ashutdown(self) -> None:
        """Async shutdown wrapper."""
        await asyncio.to_thread(self.shutdown)

    def ping(
        self,
        serial_number: str,
        topic: str,
        protocol: int = 0,
        timeout: float | None = None,
    ) -> None:
        """Ping (update) the mower."""
        cmd = {"cmd": Command.FORCE_REFRESH}
        self._log.debug("Sending '%s' on topic '%s'", cmd, topic)
        self.publish(serial_number, topic, cmd, protocol, timeout=timeout)

    async def aping(
        self,
        serial_number: str,
        topic: str,
        protocol: int = 0,
        timeout: float | None = None,
    ) -> None:
        """Async ping wrapper."""
        await asyncio.to_thread(self.ping, serial_number, topic, protocol, timeout)

    def command(
        self,
        serial_number: str,
        topic: str,
        action: Command,
        protocol: int = 0,
        timeout: float | None = None,
    ) -> None:
        """Send a specific command to the mower."""
        self.publish(
            serial_number=serial_number,
            topic=topic,
            message={"cmd": action},
            protocol=protocol,
            timeout=timeout,
        )

    async def acommand(
        self,
        serial_number: str,
        topic: str,
        action: Command,
        protocol: int = 0,
        timeout: float | None = None,
    ) -> None:
        """Async command wrapper."""
        await asyncio.to_thread(
            self.command, serial_number, topic, action, protocol, timeout
        )

    def publish(
        self,
        serial_number: str,
        topic: str,
        message: dict,
        protocol: int = 0,
        timeout: float | None = None,
    ) -> None:
        """Publish a message to the mower and wait for response."""
        effective_timeout = self._response_timeout if timeout is None else timeout
        if effective_timeout <= 0:
            raise ValueError("timeout must be greater than 0")

        self._ensure_connection_ready(effective_timeout)
        client = self.client
        if client is None:
            raise NoConnectionError("MQTT client is not available")

        command_signature = (
            serial_number,
            topic,
            protocol,
            json.dumps(message, sort_keys=True, separators=(",", ":")),
        )
        if self._deduplicate_inflight_commands and self._command_lock.locked():
            with self._response_lock:
                if self._pending_command_signature == command_signature:
                    self._log.debug(
                        "Dropping duplicate in-flight command serial=%s topic=%s protocol=%s message=%s",
                        serial_number,
                        topic,
                        protocol,
                        message,
                    )
                    return

        # Format the message
        formatted_message = self.format_message(serial_number, message, protocol)
        command_message_id = json.loads(formatted_message)["id"]
        identifier_type = "sn" if protocol == 0 else "uuid" if protocol == 1 else "id"
        self._last_command_payload = {
            "serial": serial_number,
            "identifier_type": identifier_type,
            "topic": topic,
            "message": message,
            "protocol": protocol,
            "command_id": command_message_id,
            "payload": formatted_message,
        }
        self._log.debug(
            "Publishing message id=%s serial=%s topic=%s payload=%s",
            command_message_id,
            serial_number,
            topic,
            formatted_message,
        )

        # Only allow one in-flight command until response/timeout.
        with self._command_lock:
            with self._response_lock:
                self._pending_response_target = serial_number
                self._pending_response_message_id = command_message_id
                self._pending_command_signature = command_signature
                self._response_event.clear()

            try:
                # Publish the message
                publish_future, _ = client.publish(
                    topic=topic, payload=formatted_message, qos=QOS_FLAG
                )

                # Wait for the message to be published
                publish_future.result()

                if not self._response_event.wait(effective_timeout):
                    payload = self._last_command_payload or {}
                    self._log.warning(
                        "Timeout waiting for device response; identifier_type=%s identifier=%s protocol=%s command_id=%s topic=%s payload=%s",
                        payload.get("identifier_type", identifier_type),
                        payload.get("serial", serial_number),
                        payload.get("protocol", protocol),
                        payload.get("command_id"),
                        payload.get("topic"),
                        payload.get("payload"),
                    )
                    raise TimeoutException(
                        f"Timed out waiting for device response from '{serial_number}'"
                    )
            finally:
                with self._response_lock:
                    self._pending_response_target = None
                    self._pending_response_message_id = None
                    self._pending_command_signature = None
                    self._response_event.clear()

    def _wait_until_ready(self, timeout: float) -> bool:
        """Wait for the MQTT connection to become ready."""
        ready_event = self._get_ready_event()
        if self.connected or ready_event.is_set():
            return True
        return ready_event.wait(timeout)

    def _ensure_connection_ready(self, timeout: float) -> None:
        """Ensure a usable MQTT connection exists before publishing."""
        if self.connected:
            return

        if self._token_update_lock.locked():
            if self._wait_until_ready(timeout):
                return
            raise TimeoutException("MQTT connection unavailable during token refresh")

        client = self.client
        if client is not None and not hasattr(client, "connect"):
            # Lightweight test doubles can inject a publish-only client and mark the
            # transport as connected without implementing full reconnect support.
            if self.connected:
                self._get_ready_event().set()
                return
            raise NoConnectionError("MQTT client is not available for reconnect")

        self.update_token()
        if self.connected:
            return
        raise NoConnectionError("MQTT connection is not ready")

    async def apublish(
        self,
        serial_number: str,
        topic: str,
        message: dict,
        protocol: int = 0,
        timeout: float | None = None,
    ) -> None:
        """Async publish wrapper."""
        await asyncio.to_thread(
            self.publish, serial_number, topic, message, protocol, timeout
        )

    def format_message(self, serial_number: str, message: dict, protocol: int) -> str:
        """
        Format a message.
        Message is expected to be a dict like this: {"cmd": 1}
        """
        with self._message_id_lock:
            message_id = 1024 + (next(self._message_id_seq) - 1024) % (65535 - 1024 + 1)

        now = datetime.now()
        msg = {}
        if protocol == 0:
            msg = {
                "id": message_id,
                "sn": serial_number,
                "tm": now.strftime("%H:%M:%S"),
                "dt": now.strftime("%d/%m/%Y"),
            }
        elif protocol == 1:
            utc_now = datetime.now(timezone.utc)
            msg = {
                "id": message_id,
                "uuid": serial_number,
                "tm": utc_now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        else:
            raise ValueError(f"Unsupported protocol: {protocol}")

        msg.update(message)
        self._log.debug("Formatting message '%s' to '%s'", message, msg)

        return json.dumps(msg)
