"""Basic test file."""

import asyncio
import logging
from os import environ

from pyworxcloud import WorxCloud

logging.basicConfig(level=logging.DEBUG)

EMAIL = environ["EMAIL"]
PASS = environ["PASSWORD"]
TYPE = environ["TYPE"]

# Clear the screen for better visibility when debugging
print("\033c", end="")


async def main() -> None:
    # Initialize the class
    cloud = WorxCloud(EMAIL, PASS, TYPE, tz="Europe/Copenhagen")
    await cloud.authenticate()
    await cloud.connect()

    for _, device in cloud.devices.items():
        # await cloud.update(device.serial_number)
        print(f"{device.name} online: {device.online}")

        # await cloud.set_offlimits(device.serial_number, False)
        # await cloud.set_offlimits_shortcut(device.serial_number, True)
        # await cloud.set_cutting_height(device.serial_number, 45)
        # print(f"Cutting height: {cloud.get_cutting_height(device.serial_number)}")
        # await cloud.set_acs(device.serial_number, False)

    await cloud.disconnect()


asyncio.run(main())
