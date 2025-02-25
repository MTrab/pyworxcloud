"""Testfile demonstrating the "with method" of calling the module."""

from os import environ
from pprint import pprint

from pyworxcloud import WorxCloud
from pyworxcloud.events import LandroidEvent
from pyworxcloud.utils.devices import DeviceHandler

EMAIL = environ["EMAIL"]
PASS = environ["PASSWORD"]
TYPE = environ["TYPE"]


def receive_data(
    self, name: str, device: DeviceHandler  # pylint: disable=unused-argument
) -> None:
    """Callback function when the MQTT broker sends new data."""
    for _, device in cloud.devices.items():
        pprint(vars(device))


with WorxCloud(EMAIL, PASS, TYPE) as cloud:
    for _, device in cloud.devices.items():
        cloud.update(device.serial_number)
        pprint(vars(device))

        cloud.set_callback(LandroidEvent.DATA_RECEIVED, receive_data)
