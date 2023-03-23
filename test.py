import asyncio
import datetime
import time
from os import environ

from pyworxcloud import WorxCloud

EMAIL = environ["EMAIL"]
PASS = environ["PASSWORD"]
TYPE = environ["TYPE"]

tz = datetime.datetime.now().astimezone().tzinfo.tzname(None)

# Clear the screen for better visibility when debugging
print("\033c", end="")

# Initialize the class
cloud = WorxCloud(EMAIL, PASS, TYPE)
cloud.connect()

cloud.update(cloud.mowers[0]["serial_number"])

has_data = False
while 1:
    print("\033c", end="")
    for mower in cloud.mowers:
        if not mower["has_data"]:
            print(f"{mower['name']} has not reported any state")
        else:
            print(
                f"{mower['name']} was last updated at {mower['cfg']['tm']} {mower['cfg']['dt']}"
            )

# while not cloud.mowers[0]['has_data']:
#     print(".",end="")

# print("")
# print(
#     f"{cloud.mowers[0]['name']} was last updated at {cloud.mowers[0]['cfg']['tm']} {cloud.mowers[0]['cfg']['dt']}"
# )
time.sleep(10)
cloud.disconnect()
