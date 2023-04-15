import asyncio
import datetime
import json
import time
from os import environ

from pyworxcloud import WorxCloud
from pyworxcloud.events import LandroidEvent
from pyworxcloud.utils import DeviceHandler

EMAIL = environ["EMAIL"]
PASS = environ["PASSWORD"]
TYPE = environ["TYPE"]

tz = datetime.datetime.now().astimezone().tzinfo.tzname(None)


async def main():
    loop = asyncio.get_running_loop()
    await async_worx()


async def async_worx():
    # Clear the screen for better visibility when debugging

    # Initialize the class and connect
    cloud = WorxCloud(EMAIL, PASS, TYPE)
    cloud.authenticate()
    cloud.connect()
    cloud.set_callback(LandroidEvent.DATA_RECEIVED, receive_data)

    device = cloud.devices["Robert"]
    cloud.update(device.serial_number)

    print("Listening for new data")
    while 1:
        pass

    # Self explanatory - disconnect from the cloud
    cloud.disconnect()

def receive_data(
        self, name: str, device: DeviceHandler  # pylint: disable=unused-argument
    ) -> None:
        """Callback function when the MQTT broker sends new data."""
        print("Got data on MQTT from " + name)

asyncio.run(main())
