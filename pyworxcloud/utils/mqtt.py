"""MQTT information class."""
from __future__ import annotations

import time
from typing import Mapping

import paho.mqtt.client as mqtt
from paho.mqtt.client import MQTTMessageInfo


from ..exceptions import MQTTException
from ..helpers import get_logger
from .landroid_class import LDict

_LOGGER = get_logger("mqtt")

MQTT_IN = "{}/{}/commandIn"
MQTT_OUT = "{}/{}/commandOut"


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

    def __init__(self, topic_in: str | None = None, topic_out: str | None = None):
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


# class MQTTData(LDict):
#     """Class for handling MQTT information."""

#     __topics: MQTTTopics = MQTTTopics()
#     __logger_enabled: bool = False

#     def __init__(self):
#         """Init MQTT info class."""
#         super().__init__()
#         self["messages"] = MQTTMessages()
#         self["endpoint"] = None
#         self["registered"] = None
#         self["connected"] = False

#     @property
#     def logger(self) -> bool:
#         """Return if logger is enabled or not."""
#         return self.__logger_enabled

#     @logger.setter
#     def logger(self, value: bool) -> None:
#         """Set logger state."""
#         self.__logger_enabled = value

#     @property
#     def topics(self) -> dict:
#         """Return topics dict."""
#         return self.__topics

#     @topics.setter
#     def topics(self, value: dict) -> None:
#         """Set topics values."""
#         for k, v in value.items() if isinstance(value, Mapping) else value:
#             self.__topics.update({k: v})


class MQTT(mqtt.Client, LDict):
    """Full MQTT handler class."""

    def __init__(
        self,
        devices=None,
        client_id: str = None,
        clean_session=None,
        userdata=None,
        protocol=mqtt.MQTTv311,
        transport="tcp",
        reconnect_on_failure=True,
    ):
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

        # self.device_topics = {}
        # for device in master.devices.items():
        #     self.device_topics.update({device[0]: device[1].mqtt_topics})

        self.devices = devices

        self.endpoint = None
        self.connected = False

        self.topics = {}
        for name, device in devices.items():
            topic_in = MQTT_IN.format(device.mainboard.code, device.mac_address)
            topic_out = MQTT_OUT.format(device.mainboard.code, device.mac_address)
            self.topics.update({name: MQTTTopics(topic_in, topic_out)})

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
        _LOGGER.debug("Sending %s to %s on %s", data, recipient.name, topic)
        if not self.connected and not force:
            _LOGGER.error(
                "MQTT server was not connected, can't send message to %s",
                recipient.name,
            )
            raise MQTTException("MQTT not connected")

        try:
            status = self.publish(topic, data, qos, retain)
            _LOGGER.debug("Awaiting message to be published to %s", recipient.name)
            while not status.is_published:
                time.sleep(0.1)
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
        except Exception as exc:
            _LOGGER.error("MQTT error %s to %s.\n%s", data, recipient.name, exc)

    def command(self, device: str, action: Command) -> MQTTMessageInfo:
        """Send command to device."""
        cmd = '"cmd":{}'.format(action)
        cmd = "{" + cmd + "}"
        return self.send(device, cmd)
