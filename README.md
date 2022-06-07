<a href="https://www.buymeacoffee.com/mtrab" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy Me A Coffee" style="height: 41px !important;width: 174px !important;box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;-webkit-box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;" ></a>

# pyWorxCloud

This is a PyPI module for communicating with Worx Cloud mowers, primarily developed for use with [Home Assistant](https://home-assistant.io), but I try to keep it as wide usable as possible.<br/>
<br/>
The module are compatible with cloud enabled devices from these vendors:<br/>
- Worx Landroid
- LandXcape
- Kress

This is using and undocumented API, so do not expect everything to work.<br/>
The module will be enhanced with more functionality as the API gets mapped out - any help will be much appreciated.

### Available calls

Call | Description | Parameters
---|---|---
initialize | Initialize the API connection and authenticate the user credentials |
connect | Connect to a device | index: int, verify_ssl: bool
set_callback | If set, the module will call this function when data is received from the API | callback
enumerate | Returns the number of devices associated with the account |
send | Send custom data to the API | data: str (JSON string!)
update | Retrieve current status from API |
start | Start mowing routine |
pause | Pause mowing |
home | Stop (and go home) |
zonetraining | Start zonetraining |
lock | Toggle device lock |
restart | Reboot baseboard OS |
raindelay | Set new rain delay | rain_delay: str or int
toggle_schedule | Toggle schedule on or off |
toggle_partymode | Toggle party mode if supported by device |
ots | Start OTS | boundary: bool, runtime: str or int
setzone | Set next zone to mow | zone: str or int

### Connection example
```
from pyworxcloud import WorxCloud
from pprint import pprint

cloud = WorxCloud("your@email", "password", "worx")

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
```

or like this:

```
from pyworxcloud import WorxCloud
from pprint import pprint

if __name__ == '__main__':
    with WorxCloud("your@email","password","worx", 0, False) as cloud:
        pprint(vars(cloud))
