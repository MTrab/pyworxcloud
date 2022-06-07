import asyncio
import pyworxcloud
import time

from sys import exit
from pprint import pprint
from os import environ

EMAIL = environ["EMAIL"]
PASS = environ["PASSWORD"]
TYPE = "worx"

async def main():
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
    None, worx_test)

def worx_test():
    worx = pyworxcloud.WorxCloud()

    auth = worx.initialize(EMAIL, PASS)

    if auth:
        worx.connect(0, False)
        while True:
            try:
                print("Updating Worx")
                # worx.update()
                worx.getStatus()
                print(f" - Update of {worx.name} done")
            except TimeoutError:
                print(" - Timed out waiting for response")
            except:
                print(" - Ooops - something went wrong!")

            print("Sleeping 300 seconds")
            time.sleep(300)

asyncio.run(main())