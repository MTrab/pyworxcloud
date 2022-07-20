"""MQTT information class."""
from __future__ import annotations

import asyncio
import math
import re
from datetime import datetime, timedelta
from typing import Any

import paho.mqtt.client as mqtt
from paho.mqtt.client import MQTTMessageInfo
from ratelimit import RateLimitException, rate_limited

from ..events import EventHandler, LandroidEvent
from ..exceptions import MQTTException
from ..helpers import get_logger
from .landroid_class import LDict

_LOGGER = get_logger("mqtt")

MQTT_IN = "{}/{}/commandIn"
MQTT_OUT = "{}/{}/commandOut"

PUBLISH_LIMIT_PERIOD = 60  # s
PUBLISH_CALLS_LIMIT = 5  # polls per timeframe


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


class MQTTQueue:
    """Class for handling queue."""

    def __init__(self):
        """Initialize queue object."""
        self.callback: Any | None = None
        self.retry_at = datetime.now()
        self.items = list[MQTTMessageItem]()


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

    START = 1
    PAUSE = 2
    HOME = 3
    ZONETRAINING = 4
    LOCK = 5
    UNLOCK = 6
    RESTART = 7
    PAUSE_OVER_WIRE = 8
    SAFEHOME = 9


class MQTT(mqtt.Client, LDict):
    """Full MQTT handler class."""

    __loop: asyncio.AbstractEventLoop | None = None
    __loop_allow: bool = True

    def __init__(
        self,
        devices: Any | None = None,
        client_id: str | None = None,
        clean_session: Any | None = None,
        userdata: Any | None = None,
        protocol: Any = mqtt.MQTTv311,
        transport: str = "tcp",
        reconnect_on_failure: bool = True,
    ) -> dict:
        if isinstance(devices, type(None)):
            return

        super().__init__(
            client_id,
            clean_session,
            userdata,
            protocol,
            transport,
            reconnect_on_failure,
        )

        self._events = EventHandler()

        self.rl_send = rate_limited(PUBLISH_CALLS_LIMIT, PUBLISH_LIMIT_PERIOD)(
            self.__send
        )

        self.devices = devices

        self.endpoint = None
        self.connected = False

        self.queue = MQTTQueue()
        self.topics = {}
        for name, device in devices.items():
            topic_in = MQTT_IN.format(device.mainboard.code, device.mac_address)
            topic_out = MQTT_OUT.format(device.mainboard.code, device.mac_address)
            self.topics.update({name: MQTTTopics(topic_in, topic_out)})

        # try:
        #     self.__loop = asyncio.get_event_loop()
        #     self.__loop.run_in_executor(None, self.__handle_queue)
        # except RuntimeError:
        #     return

    def set_topics(self, name: str, commandIn: str, commandOut: str) -> None:
        """Set the MQTT topics."""
        self.topics.update({name: MQTTTopics(commandIn, commandOut)})

    def set_eventloop(self, eventloop: Any) -> None:
        """Set eventloop to be used ny queue handler."""
        self.__loop = eventloop
        self.__loop.run_in_executor(None, self.__handle_queue)

    def stop_queuehandler(self) -> None:
        """Stops the eventloop for the queue handler."""
        self.queue.callback = None
        self.__loop_allow = False

    def disconnect(self, reasoncode=None, properties=None):
        self.__loop_allow = False
        self.loop_stop()
        return super().disconnect(reasoncode, properties)

    def __handle_queue(self):
        """Handle the MQTT queue."""
        while self.__loop_allow:
            if isinstance(self.queue.retry_at, int):
                continue

            if self.queue.retry_at < datetime.now() and len(self.queue.items) > 0:
                queue_list = list(reversed(self.queue.items))
                self.queue.items.clear()
                while queue_list:
                    message = queue_list.pop()
                    log_msg = f'Trying message "{message}" from the message queue'
                    if not self._events.call(
                        LandroidEvent.MQTT_RATELIMIT, message=log_msg
                    ):
                        _LOGGER.debug(log_msg)
                    self.send(
                        device=message["device"],
                        data=message["data"],
                        qos=message["qos"],
                        retain=message["retain"],
                    )

    def __send(
        self,
        topic: str,
        data: str = "{}",
        qos: int = 0,
        retain: bool = False,
    ) -> MQTTMessageInfo:
        """Do the actual publish."""
        return self.publish(topic, data, qos, retain)

    def send(
        self,
        device: str,
        data: str = "{}",
        qos: int = 0,
        retain: bool = False,
        force: bool = False,
    ) -> MQTTMessageInfo | str:
        """Send Landroid cloud message to API endpoint."""
        from .devices import DeviceHandler

        recipient: DeviceHandler = self.devices[device]
        topic = self.topics[device]["in"]

        data = data.replace("'", '"')
        if not re.match('^\{[A-ZÆØÅa-zæøå0-9:,\[\]"{} \n-]*\}$', data):
            data = "{" + data + "}"

        log_msg = f'Sending "{data}" to "{recipient.name}" on "{topic}"'
        if not self._events.call(LandroidEvent.LOG, message=log_msg, level="debug"):
            _LOGGER.debug(log_msg)

        if not self.connected and not force:
            log_msg = (
                f"MQTT server was not connected, can"
                't send message to "{recipient.name}"'
            )
            if not self._events.call(LandroidEvent.LOG, message=log_msg, level="error"):
                _LOGGER.error(log_msg)

            raise MQTTException("MQTT not connected")

        message = MQTTMessageItem(device, data, qos, retain)

        self._events.call(
            LandroidEvent.MQTT_PUBLISH,
            message=data,
            device=device,
            topic=topic,
            qos=qos,
            retain=retain,
        )

        try:

            status = self.rl_send(topic, data, qos, retain)
            log_msg = (
                f'Awaiting message to be published to "{recipient.name}" on "{topic}"'
            )
            if not self._events.call(LandroidEvent.LOG, message=log_msg, level="debug"):
                _LOGGER.debug(log_msg)

            while not status.is_published:
                pass  # Await status to change to is_published

            log_msg = f'MQTT message was published to "{recipient.name}" on "{topic}"'
            if not self._events.call(LandroidEvent.LOG, message=log_msg, level="debug"):
                _LOGGER.debug(log_msg)

            return status
        except ValueError as exc:
            log_msg = f'MQTT queue for "{recipient.name}" was full, message "{data}" was not sent!'
            if not self._events.call(LandroidEvent.LOG, message=log_msg, level="error"):
                _LOGGER.error(log_msg)
        except RuntimeError as exc:
            log_msg = f'MQTT error while sending message "{data}" to "{recipient.name}"\n{exc}'
            if not self._events.call(LandroidEvent.LOG, message=log_msg, level="error"):
                _LOGGER.error(log_msg)
        except RateLimitException as exc:
            _LOGGER.debug("Adding '%s' to message queue.", message)
            self.queue.retry_at = datetime.now() + timedelta(
                seconds=math.ceil(exc.period_remaining)
            )
            self.queue.items.append(message)
            self._events.call(
                LandroidEvent.MQTT_RATELIMIT,
                message=f"Ratelimit of {PUBLISH_CALLS_LIMIT} messages in {PUBLISH_LIMIT_PERIOD} seconds exceeded. Message '{message['data']}' to '{message['device']}' added to message queue.",
            )
            return f"Ratelimit of {PUBLISH_CALLS_LIMIT} messages in {PUBLISH_LIMIT_PERIOD} seconds exceeded. Wait {math.ceil(exc.period_remaining)} seconds before trying again"
        except Exception as exc:
            log_msg = f'MQTT error sending "{data}" to "{recipient.name}"'
            if not self._events.call(LandroidEvent.LOG, message=log_msg, level="error"):
                _LOGGER.error(log_msg)

    def set_ratelimit(self, messages: int, seconds: int) -> None:
        """Set ratelimits.

        messages (int): Number of messages before ratelimiting
        seconds (int): Number of seconds the ratelimit is counting towards
        """
        self.rl_send = rate_limited(messages, seconds)(self.__send)

    def command(self, device: str, action: Command) -> MQTTMessageInfo:
        """Send command to device."""
        cmd = '"cmd":{}'.format(action)
        cmd = "{" + cmd + "}"
        return self.send(device, cmd)
