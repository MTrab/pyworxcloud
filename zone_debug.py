import logging
import time
from os import environ

from pyworxcloud import WorxCloud

EMAIL = environ["EMAIL"]
PASS = environ["PASSWORD"]
TYPE = environ["TYPE"]


def present_zone(device: WorxCloud, zone) -> str:
    current, new_zones, current_index, next_index = device.setzone(zone, debug=True)

    ruler = "[0] [1] [2] [3] [4] [5] [6] [7] [8] [9]"

    sequence = ""
    for zone_index in new_zones:
        sequence += f"[{str(zone_index)}] "

    pointer = ""
    npointer = ""
    for i in range(len(new_zones)):
        if i == current_index:
            pointer += "/|\\ "
        else:
            pointer += "    "

        if i == next_index:
            npointer += "/|\\ "
        else:
            npointer += "    "

    retval = f"""
                   Ruler: {ruler}
           Zone sequence: {sequence}
    Current zone pointer: {pointer}
       Next zone pointer: {npointer}
    """
    return retval


with WorxCloud(EMAIL, PASS, TYPE, verify_ssl=False) as cloud:
    time.sleep(2)
    cloud._log.setLevel(logging.WARNING)
    print("\033c", end="")
    device = cloud.devices["R2D2"]

    while 1:
        zone = input("Please enter the next zone to be handled: ")
        print(present_zone(device, zone))
