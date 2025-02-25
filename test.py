"""Basic test file."""

from os import environ
from pprint import pprint

from pyworxcloud import WorxCloud

EMAIL = environ["EMAIL"]
PASS = environ["PASSWORD"]
TYPE = environ["TYPE"]

# Clear the screen for better visibility when debugging
print("\033c", end="")

# Initialize the class
cloud = WorxCloud(EMAIL, PASS, TYPE)
cloud.authenticate()
cloud.connect()

# print(vars(cloud))

for _, device in cloud.devices.items():
    cloud.update(device.serial_number)
    pprint(vars(device))
    print(f"{device.name} online: {device.online}")

cloud.disconnect()
