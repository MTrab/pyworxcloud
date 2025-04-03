"""Basic test file."""

from os import environ
from pprint import pprint

from pyworxcloud import WorxCloud

EMAIL = environ["EMAIL"]
PASS = environ["PASSWORD"]
TYPE = environ["TYPE"]

# Clear the screen for better visibility when debugging
print("\033c", end="")

iter = 1
max = 1

while iter <= max:
    # Initialize the class
    cloud = WorxCloud(EMAIL, PASS, TYPE, tz="Europe/Copenhagen")
    cloud.authenticate()
    cloud.connect()
    for _, device in cloud.devices.items():
        cloud.update(device.serial_number)
        # pprint(vars(device))
        print(f"{device.name} online: {device.online}")

        # cloud.set_offlimits(device.serial_number, False)
        # cloud.set_offlimits_shortcut(device.serial_number, True)

    cloud.disconnect()
    iter += 1
