from os import environ
from pprint import pprint

from pyworxcloud import WorxCloud

EMAIL = environ["EMAIL"]
PASS = environ["PASSWORD"]
TYPE = environ["TYPE"]

with WorxCloud(EMAIL, PASS, TYPE) as cloud:
    for _, device in cloud.devices.items():
        cloud.update(device.serial_number)
        pprint(vars(device))
