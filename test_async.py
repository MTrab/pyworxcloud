import asyncio
import datetime
import json
import time
from os import environ

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

    # Initialize the class and connect
    cloud = WorxCloud(EMAIL, PASS, TYPE)
    cloud.connect()

    # Initialize a indicator for the last msg ID received from the API
    last_id = None
    while 1:
        # Only print new state if the msg ID was different than the last that was displayed
        if not cloud.mowers[0]["last_message_id"] == last_id:

            # Set last_id to the new msg ID
            last_id = cloud.mowers[0]["last_message_id"]

            # Clear the screen
            print("\033c", end="")

            # Print all attributes
            print(json.dumps(cloud.mowers[0], indent=4, sort_keys=True, default=str))

        # Let the thread sleep for 5 seconds as to not overload the computer.
        time.sleep(5)

    # Self explanatory - disconnect from the cloud
    cloud.disconnect()


asyncio.run(main())
