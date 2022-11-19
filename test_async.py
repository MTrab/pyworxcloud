import asyncio
import datetime
import json
from os import environ
import time

from pyworxcloud import WorxCloud

EMAIL = environ["EMAIL"]
PASS = environ["PASSWORD"]
TYPE = environ["TYPE"]

tz = datetime.datetime.now().astimezone().tzinfo.tzname(None)


async def main():
    loop = asyncio.get_running_loop()
    await async_worx()


async def async_worx():
    # Clear the screen for better visibility when debugging
    print("\033c", end="")

    # Initialize the class
    cloud = WorxCloud(EMAIL, PASS, TYPE)
    cloud.connect()

    cloud.update(cloud.mowers[0]["serial_number"])

    while 1:
        print("\033c", end="")
        print(json.dumps(cloud.mowers[0],indent=4))

        time.sleep(5)

    cloud.disconnect()


asyncio.run(main())
