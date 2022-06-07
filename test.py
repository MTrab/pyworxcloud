from pyworxcloud import WorxCloud
from pprint import pprint
from os import environ

EMAIL = environ["EMAIL"]
PASS = environ["PASSWORD"]
TYPE = "worx"

print()
if __name__ == '__main__':
    
    with WorxCloud(EMAIL,PASS,TYPE) as cloud:
        pprint(vars(cloud))
