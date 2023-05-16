"""Basic test file."""
import datetime
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
cloud.authenticate()
cloud.connect()

cloud.setzone("20213028401100013915", 2)

# print(vars(cloud))

cloud.disconnect()
