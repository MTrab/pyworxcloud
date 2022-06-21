"""MQTT information class."""

import json
from typing import Any, Mapping, overload
import paho.mqtt.client as mqtt
from paho.mqtt.client import MQTTMessageInfo

from .landroid_class import LDict


class MQTTMsgType(LDict):
    """Define specific message type data."""

    def __init__(self):
        super().__init__()

        self["in"] = 0
        self["out"] = 0


class MQTTMessages(LDict):
    """Messages class."""

    def __init__(self):
        super().__init__()

        self["raw"] = MQTTMsgType()
        self["filtered"] = MQTTMsgType()


class MQTTTopics(LDict):
    """Topics class."""

    def __init__(self):
        super().__init__()

        self["in"] = None
        self["out"] = None


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


class MQTTHandler(mqtt.Client):
    """MQTT communications handler."""

    __topics: MQTTTopics = MQTTTopics()

    @overload
    def __init__(self):
        # self.client = None
        self.__topics = MQTTTopics()

    def __init__(
        self,
        client_id="",
        clean_session=None,
        userdata=None,
        protocol=...,
        transport="tcp",
        reconnect_on_failure=True,
    ) -> None:
        self.client = super().__init__(
            client_id,
            clean_session,
            userdata,
            protocol,
            transport,
            reconnect_on_failure,
        )

    @property
    def topics(self) -> dict:
        """Return topics dict."""
        return self.__topics

    @topics.setter
    def topics(self, value: dict) -> None:
        """Set topics values."""
        for k, v in value.items() if isinstance(value, Mapping) else value:
            self.__topics.update({k: v})

    def send(
        self,
        data: str = "{}",
        qos: int = 0,
        retain: bool = False,
    ) -> MQTTMessageInfo:
        """Send Landroid cloud message to API endpoint."""
        return self.publish(self.topics["in"], data, qos, retain)

    def command(self, action: Command) -> MQTTMessageInfo:
        """Send command to device."""
        return self.send(f'{{"cmd": {action}}}')


class MQTTData(MQTTHandler, LDict):
    """Class for handling MQTT information."""

    # __slots__ = "endpoint", "topics"

    def __init__(self):
        """Init MQTT info class."""
        super().__init__()

        self["messages"] = MQTTMessages()
        self["endpoint"] = None
        self["registered"] = None
