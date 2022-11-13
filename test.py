import asyncio
import datetime
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

    for mower in cloud.mowers:
        cloud.update(mower["serial_number"])

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

        time.sleep(10)

    cloud.disconnect()


asyncio.run(main())
