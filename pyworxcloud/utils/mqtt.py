"""MQTT information class."""
from typing import Mapping
import paho.mqtt.client as mqtt
from paho.mqtt.client import MQTTMessageInfo

from ..helpers import get_logger
from .landroid_class import LDict

_LOGGER = get_logger("mqtt")


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
        name: str = None,
    ):
        super().__init__(
            client_id,
            clean_session,
            userdata,
            protocol,
            transport,
            reconnect_on_failure,
        )
        self.__connected = False

        self.topics = topics
        self.name = name

    @property
    def connected(self) -> bool:
        """Return connection state."""
        return self.__connected

    @connected.setter
    def connected(self, state: bool) -> None:
        """Set connected flag."""
        self.__connected = state

    def send(
        self,
        data: str = "{}",
        qos: int = 0,
        retain: bool = False,
    ) -> MQTTMessageInfo:
        """Send Landroid cloud message to API endpoint."""
        _LOGGER.debug("Sending %s to %s", data, self.name)
        if not self.connected:
            _LOGGER.error(
                "MQTT server was not connected, can't send message to %s", self.name
            )
            return None

        try:
            status = self.publish(self.topics["in"], data, qos, retain)
            status.wait_for_publish(10)
        except ValueError:
            _LOGGER.error(
                "MQTT queue for %s was full, message %s was not sent!", self.name, data
            )
        except RuntimeError as exc:
            _LOGGER.error(
                "MQTT error while sending message %s to %s.\n%s", data, self.name, exc
            )
        finally:
            return status

    def command(self, action: Command) -> MQTTMessageInfo:
        """Send command to device."""
        return self.send(f'"cmd": {action}')


class MQTTTest(LDict):
    """Full MQTT handler class."""

    def __init__(
        self,
        mqtt: mqtt.Client = None,
        topics: dict = {},
        name: str = "Unknown",
    ):
        super().__init__()
        self.mqtt = mqtt
        self.topics = topics
        self.name = name

    def send(
        self,
        data: str = "{}",
        qos: int = 0,
        retain: bool = False,
    ) -> MQTTMessageInfo:
        """Send Landroid cloud message to API endpoint."""
        _LOGGER.debug("Sending %s to %s", data, self.name)
        try:
            status = self.mqtt.publish(self.topics["in"], data, qos, retain)
            status.wait_for_publish(10)
        except ValueError:
            _LOGGER.error(
                "MQTT queue for %s was full, message %s was not sent!", self.name, data
            )
        except RuntimeError as exc:
            _LOGGER.error(
                "MQTT error while sending message %s to %s.\n%s", data, self.name, exc
            )
        finally:
            return status

    def command(self, action: Command) -> MQTTMessageInfo:
        """Send command to device."""
        return self.send(f'{{"cmd": {action}}}')
