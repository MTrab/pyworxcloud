from pyworxcloud import WorxCloud
from pprint import pprint
from os import environ

EMAIL = environ["EMAIL"]
PASS = environ["PASSWORD"]
TYPE = "worx"

if __name__ == '__main__':
    with WorxCloud(EMAIL,PASS,TYPE, verify_ssl=False) as cloud:
        pprint(vars(cloud))
