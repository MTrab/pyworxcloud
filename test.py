import time
from os import environ
from pprint import pprint

from pyworxcloud import WorxCloud

EMAIL = environ["EMAIL"]
PASS = environ["PASSWORD"]
TYPE = environ["TYPE"]


if __name__ == "__main__":
    # Clear the screen for better visibility when debugging
    print("\033c", end="")

    # Initialize the class
    cloud = WorxCloud(EMAIL, PASS, TYPE)

    # Initialize connection
    auth = cloud.authenticate()

    if not auth:
        # If invalid credentials are used, or something happend during
        # authorize, then exit
        exit(0)

    # Connect to device with index 0 (devices are enumerated 0, 1, 2 ...) and do
    # not verify SSL (False)
    cloud.connect(verify_ssl=False, pahologger=True)

    # Wait for MQTT connection
    while not cloud.mqtt.connected:
        pass

    # Read latest states received from the device
    cloud.update()

    # cloud._mqtt.publish("DB510/F0FE6B83B4A8/commandIn", '{}', 0, False)
    # cloud.mqtt.send()
    # cloud.home()
    # Print all vars and attributes of the cloud object
    for index, (name, device) in enumerate(cloud.devices.items()):
        # device.start()
        # device.raindelay(30)
        # time.sleep(5)
        # device.mqtt.send(name)
        # cloud.update()
        pprint(vars(device))
    # print(cloud.mqttdata)

    # cloud.disconnect()
