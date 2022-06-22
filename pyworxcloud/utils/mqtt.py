"""MQTT information class."""
import logging
from typing import Mapping
import paho.mqtt.client as mqtt
from paho.mqtt.client import MQTTMessageInfo

from .landroid_class import LDict

_LOGGER = logging.getLogger(__name__)


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


class MQTTData(LDict):
    """Class for handling MQTT information."""

    __topics: MQTTTopics = MQTTTopics()

    def __init__(self):
        """Init MQTT info class."""
        super().__init__()
        self["messages"] = MQTTMessages()
        self["endpoint"] = None
        self["registered"] = None

    @property
    def topics(self) -> dict:
        """Return topics dict."""
        return self.__topics

    @topics.setter
    def topics(self, value: dict) -> None:
        """Set topics values."""
        for k, v in value.items() if isinstance(value, Mapping) else value:
            self.__topics.update({k: v})


class MQTT(mqtt.Client, LDict):
    """Full MQTT handler class."""

    def __init__(
        self,
        client_id="",
        clean_session=None,
        userdata=None,
        protocol=mqtt.MQTTv311,
        transport="tcp",
        reconnect_on_failure=True,
        topics: dict = {},
    ):
        super().__init__(
            client_id,
            clean_session,
            userdata,
            protocol,
            transport,
            reconnect_on_failure,
        )
        self.topics = topics

    def send(
        self,
        data: str = "{}",
        qos: int = 0,
        retain: bool = False,
    ) -> MQTTMessageInfo:
        """Send Landroid cloud message to API endpoint."""
        print(f"Publishing {data} to {self.topics['in']}")
        result = self.publish(self.topics["in"], data, qos, retain)
        # print(result)
        return result

    def command(self, action: Command) -> MQTTMessageInfo:
        """Send command to device."""
        return self.send(f'{{"cmd": {action}}}')
