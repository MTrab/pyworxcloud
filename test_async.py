import asyncio
import time
from os import environ
from pprint import pprint

from pyworxcloud import WorxCloud

EMAIL = environ["EMAIL"]
PASS = environ["PASSWORD"]
TYPE = "worx"


async def main():
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, worx_test)


def worx_test():
    cloud = WorxCloud(EMAIL, PASS, TYPE)

    # Initialize connection
    auth = cloud.authenticate()

    if not auth:
        # If invalid credentials are used, or something happend during
        # authorize, then exit
        exit(0)

    # Connect to device with index 0 (devices are enumerated 0, 1, 2 ...) and do
    # not verify SSL (False)
    cloud.connect(0, False)

    lastupdate = None
    cloud.update()
    while True:
        if cloud.updated != lastupdate:
            lastupdate = cloud.updated
            pprint(vars(cloud))
        # try:
        #     print("Updating Worx")
        #     # Read latest states received from the device
        #     cloud.update()

        #     # Print all vars and attributes of the cloud object
        #     pprint(vars(cloud))
        # except TimeoutError:
        #     print(" - Timed out waiting for response")
        # except:
        #     print(" - Ooops - something went wrong!")

        # print("Sleeping 300 seconds")
        # time.sleep(300)


asyncio.run(main())
