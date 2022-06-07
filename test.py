from pyworxcloud import WorxCloud
from os import environ
from pprint import pprint

EMAIL = environ["EMAIL"]
PASS = environ["PASSWORD"]
TYPE = "worx"

cloud = WorxCloud(EMAIL, PASS, TYPE)

# Initialize connection
auth = cloud.authenticate

if not auth:
    # If invalid credentials are used, or something happend during
    # authorize, then exit
    exit(0)

# Connect to device with index 0 (devices are enumerated 0, 1, 2 ...) and do
# not verify SSL (False)
cloud.connect(0, False)

# Read latest states received from the device
cloud.update()

# Print all vars and attributes of the cloud object
pprint(vars(cloud))