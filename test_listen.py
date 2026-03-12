import asyncio
import logging
from os import environ

from pyworxcloud import WorxCloud
from pyworxcloud.events import LandroidEvent
from pyworxcloud.utils import DeviceHandler

logging.basicConfig(level=logging.DEBUG)

EMAIL = environ["EMAIL"]
PASS = environ["PASSWORD"]
TYPE = environ["TYPE"]


def _resolve_cloud_timezone() -> str | None:
    """Return optional client timezone override for manual live testing."""
    timezone_name = (
        environ.get("PYWORXCLOUD_TZ")
        or environ.get("WORXCLOUD_TZ")
        or environ.get("DASHBOARD_TZ")
    )
    if timezone_name is None:
        return None
    timezone_name = timezone_name.strip()
    return timezone_name or None


async def main():
    await async_worx()


async def async_worx():
    # Clear the screen for better visibility when debugging

    # Initialize the class and connect
    cloud = WorxCloud(EMAIL, PASS, TYPE, tz=_resolve_cloud_timezone())
    await cloud.authenticate()
    await cloud.connect()
    cloud.set_callback(LandroidEvent.DATA_RECEIVED, receive_data)
    cloud.set_callback(LandroidEvent.API, receive_api_data)

    print("Listening for new data")
    try:
        while True:
            await asyncio.sleep(1)
    finally:
        # Self explanatory - disconnect from the cloud
        await cloud.disconnect()


def receive_data(
    name: str, device: DeviceHandler  # pylint: disable=unused-argument
) -> None:
    """Callback function when the MQTT broker sends new data."""
    print("Got data on MQTT from " + name)
    print(name + " last status: " + str(device.last_status))


def receive_api_data(
    name: str, device: DeviceHandler  # pylint: disable=unused-argument
) -> None:
    """Callback function when the API data was updated."""
    print(f"API data was refreshed for {name}")


asyncio.run(main())
