import datetime
from os import environ
from pprint import pprint

from pyworxcloud import WorxCloud

EMAIL = environ["EMAIL"]
PASS = environ["PASSWORD"]
TYPE = "worx"

tz = datetime.datetime.now().astimezone().tzinfo.tzname(None)

if __name__ == "__main__":
    with WorxCloud(EMAIL, PASS, TYPE, verify_ssl=False,tz=tz) as cloud:
        pprint(vars(cloud))
