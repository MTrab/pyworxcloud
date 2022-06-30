"""MQTT information class."""
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta
import math

import re
from typing import Any

import paho.mqtt.client as mqtt
from paho.mqtt.client import MQTTMessageInfo
from ratelimit import RateLimitException, limits

from ..exceptions import MQTTException, RateLimit
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
        self.retry_at = datetime.now()
        self.items = list[MQTTMessageItem]


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

        self.devices = devices

        self.endpoint = None
        self.connected = False

        self.queue = MQTTQueue()
        self.topics = {}
        for name, device in devices.items():
            topic_in = MQTT_IN.format(device.mainboard.code, device.mac_address)
            topic_out = MQTT_OUT.format(device.mainboard.code, device.mac_address)
            self.topics.update({name: MQTTTopics(topic_in, topic_out)})

        queue_loop = asyncio.new_event_loop()
        asyncio.ensure_future(self.__async_handle_queue)
        queue_loop.run_forever()

    async def __async_handle_queue(self):
        """Handle the MQTT queue."""
        while 1:
            if self.queue.retry_at < datetime.now():
                for entry in self.queue.items:
                    message = self.queue.items.pop(entry)
                    _LOGGER.debug("Trying queue item %s", entry)
                    await asyncio.get_event_loop().run_in_executor(
                        self.send,
                        device=message["device"],
                        data=message["data"],
                        qos=message["qos"],
                        retain=message["retain"],
                    )

    @limits(calls=PUBLISH_CALLS_LIMIT, period=PUBLISH_LIMIT_PERIOD)
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
    ) -> MQTTMessageInfo:
        """Send Landroid cloud message to API endpoint."""
        from .devices import DeviceHandler

        recipient: DeviceHandler = self.devices[device]
        topic = self.topics[device]["in"]

        if not re.match("^\{[A-ZÆØÅa-zæøå0-9:'\"{} \n]*\}$", data):
            data = "{" + data + "}"

        _LOGGER.debug("Sending %s to %s on %s", data, recipient.name, topic)
        if not self.connected and not force:
            _LOGGER.error(
                "MQTT server was not connected, can't send message to %s",
                recipient.name,
            )
            raise MQTTException("MQTT not connected")

        message = MQTTMessageItem(device, data, qos, retain)

        try:
            status = self.__send(topic, data, qos, retain)
            _LOGGER.debug(
                "Awaiting message to be published to %s on %s", recipient.name, topic
            )
            while not status.is_published:
                pass  # Await status to change to is_published
                # time.sleep(0.1)
            _LOGGER.debug(
                "MQTT message was published to %s on %s", recipient.name, topic
            )
            return status
        except ValueError as exc:
            _LOGGER.error(
                "MQTT queue for %s was full, message %s was not sent!",
                recipient.name,
                data,
            )
        except RuntimeError as exc:
            _LOGGER.error(
                "MQTT error while sending message %s to %s.\n%s",
                data,
                recipient.name,
                exc,
            )
        except RateLimitException as exc:
            _LOGGER.debug("Adding '%s' to message queue.", message)
            self.queue.retry_at = datetime.now() + timedelta(
                seconds=math.ceil(exc.period_remaining)
            )
            self.queue.items.append(message)

            msg = f"Ratelimit of {PUBLISH_CALLS_LIMIT} messages in {PUBLISH_LIMIT_PERIOD} seconds exceeded. Wait {math.ceil(exc.period_remaining)} seconds before trying again"
            raise RateLimit(
                message=msg,
                limit=PUBLISH_CALLS_LIMIT,
                period=PUBLISH_LIMIT_PERIOD,
                remaining=exc.period_remaining,
            ) from exc
        except Exception as exc:
            _LOGGER.error(
                "MQTT error sending '%s' to '%s'",
                data,
                recipient.name,
            )

    def command(self, device: str, action: Command) -> MQTTMessageInfo:
        """Send command to device."""
        cmd = '"cmd":{}'.format(action)
        cmd = "{" + cmd + "}"
        return self.send(device, cmd)
