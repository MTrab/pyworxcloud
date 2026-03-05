"""pyWorxCloud definition."""

# pylint: disable=undefined-loop-variable
# pylint: disable=line-too-long
# pylint: disable=too-many-lines
from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta
from random import randint
from typing import Any
from zoneinfo import ZoneInfo

from .api import LandroidCloudAPI
from .clouds import CloudType
from .events import EventHandler, LandroidEvent
from .exceptions import (
    AuthorizationError,
    InternalServerError,
    MowerNotFoundError,
    NoACSModuleError,
    NoConnectionError,
    NoCuttingHeightError,
    NoOfflimitsError,
    NoOneTimeScheduleError,
    NoPartymodeError,
    OfflineError,
    TooManyRequestsError,
    ZoneNoProbability,
    ZoneNotDefined,
)
from .helpers import convert_to_time, get_logger
from .utils import MQTT, DeviceCapability, DeviceHandler
from .utils.mqtt import Command
from .utils.requests import APOST, HEADERS

if sys.version_info < (3, 9, 0):
    sys.exit("The pyWorxcloud module requires Python 3.9.0 or later")

_LOGGER = logging.getLogger(__name__)

API_REFRESH_TIME_MIN = 5
API_REFRESH_TIME_MAX = 10
DEFAULT_COMMAND_TIMEOUT = 30.0


class WorxCloud(dict):
    """
    Worx by Landroid Cloud connector.

    Used for handling API connection to Worx, Kress and Landxcape devices which are cloud connected.

    This uses a reverse engineered API protocol, so no guarantee that this will keep working.
    There are no public available API documentation available.
    """

    # __device: str | None = None

    def __init__(
        self,
        username: str,
        password: str,
        cloud: (
            CloudType.WORX | CloudType.KRESS | CloudType.LANDXCAPE | str
        ) = CloudType.WORX,
        verify_ssl: bool = True,
        tz: str | None = None,  # pylint: disable=invalid-name
        command_timeout: float = DEFAULT_COMMAND_TIMEOUT,
        deduplicate_inflight_commands: bool = False,
    ) -> None:
        """
        Initialize :class:WorxCloud class and set default attribute values.

        1. option for connecting and printing the current states from the API, using :code:`with`

        .. testcode::
        from pyworxcloud import WorxCloud
        from pprint import pprint

        with WorxCloud("your@email","password","worx", 0, False) as cloud:
            pprint(vars(cloud))

        2. option for connecting and printing the current states from the API, using :code:`connect` and :code:`disconnect`

        .. testcode::
        from pyworxcloud import WorxCloud
        from pprint import pprint

        cloud = WorxCloud("your@email", "password", "worx")

        # Initialize connection
        auth = cloud.authenticate()

        if not auth:
            # If invalid credentials are used, or something happend during
            # authorize, then exit
            exit(0)

        # Connect to device with index 0 (devices are enumerated 0, 1, 2 ...)
        # and do not verify SSL (False)
        cloud.connect(0, False)

        # Read latest states received from the device
        cloud.update()

        # Print all vars and attributes of the cloud object
        pprint(vars(cloud))

        # Disconnect from the API
        cloud.disconnect()

        For further information, see the Wiki for documentation: https://github.com/MTrab/pyworxcloud/wiki

        Args:
            username (str): Email used for logging into the app for your device.
            password (str): Password for your account.
            cloud (CloudType.WORX | CloudType.KRESS | CloudType.LANDXCAPE | str, optional): The CloudType matching your device. Defaults to CloudType.WORX.
            index (int, optional): Device number if more than one is connected to your account (starting from 0 representing the first added device). Defaults to 0.
            verify_ssl (bool, optional): Should this module verify the API endpoint SSL certificate? Defaults to True.

        Raise:
            TypeError: Error raised if invalid CloudType was specified.
        """
        _LOGGER.debug("Initializing connector...")
        super().__init__()

        self._worx_mqtt_client_id = None

        if not isinstance(
            cloud,
            (
                type(CloudType.WORX),
                type(CloudType.LANDXCAPE),
                type(CloudType.KRESS),
            ),
        ):
            try:
                _LOGGER.debug("Try getting correct CloudType from %s", cloud.upper())
                cloud = getattr(CloudType, cloud.upper())
                _LOGGER.debug("Found cloud type %s", cloud)
            except AttributeError:
                raise TypeError(
                    "Wrong type specified, valid types are: worx, landxcape or kress"
                ) from None

        _LOGGER.debug("Initializing the API connector ...")
        self._api = LandroidCloudAPI(username, password, cloud, tz, self._token_updated)
        self._username = username
        self._cloud = cloud
        self._auth_result = False
        _LOGGER.debug("Getting logger ...")
        self._log = get_logger("pyworxcloud")
        self._raw = None
        self._tz = tz

        self._save_zones = None
        self._verify_ssl = verify_ssl
        if command_timeout <= 0:
            raise ValueError("command_timeout must be greater than 0")
        self._command_timeout = float(command_timeout)
        self._deduplicate_inflight_commands = bool(deduplicate_inflight_commands)
        _LOGGER.debug("Initializing EventHandler ...")
        self._events = EventHandler()

        self._endpoint = None
        self._user_id = None
        self._mowers = None
        self._mowers_by_serial: dict[str, dict[str, Any]] = {}
        self._mowers_by_uuid: dict[str, dict[str, Any]] = {}
        self._mowers_by_mac: dict[str, dict[str, Any]] = {}

        self._decoding: bool = False

        self._api_refresh_task: asyncio.Task | None = None
        self._disconnecting = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._sync_loop: asyncio.AbstractEventLoop | None = None

        # Dict of devices, identified by name
        self.devices: DeviceHandler = {}

        self.mqtt = None

    async def __aenter__(self) -> Any:
        """Default actions using async with statement."""
        await self.authenticate()
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> Any:
        """Called on end of async with statement."""
        await self.disconnect()

    def __enter__(self) -> Any:
        """Compatibility helper for sync with usage."""
        self._sync_loop = asyncio.new_event_loop()
        self._sync_loop.run_until_complete(self.authenticate())
        self._sync_loop.run_until_complete(self.connect())
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> Any:
        """Called on end of with statement."""
        if self._sync_loop is not None:
            try:
                self._sync_loop.run_until_complete(self.disconnect())
            finally:
                self._sync_loop.close()
                self._sync_loop = None

    async def authenticate(self) -> bool:
        """Authenticate against the API."""
        self._log.debug("Authenticating %s", self._username)

        try:
            await self._api.get_token()
        except TooManyRequestsError:
            raise TooManyRequestsError from None

        auth = self._api.authenticate()
        if auth is False:
            self._auth_result = False
            self._log.debug("Authentication for %s failed!", self._username)
            raise AuthorizationError("Unauthorized")

        self._auth_result = True
        self._log.debug("Authentication for %s successful", self._username)

        return True

    def update_attribute(self, device: str, attr: str, key: str, value: Any) -> None:
        """Used as callback to update value."""
        chattr = self.devices[device]
        if not isinstance(attr, type(None)):
            for level in attr.split(";;"):
                if hasattr(chattr, level):
                    chattr = getattr(chattr, level)
                else:
                    chattr = chattr[level]

        if hasattr(chattr, key):
            setattr(chattr, key, value)
        elif isinstance(chattr, dict):
            chattr.update({key: value})

    def set_callback(self, event: LandroidEvent, func: Any) -> None:
        """Set callback which is called when data is received.

        Args:
            event: LandroidEvent for this callback
            func: Function to be called.
        """
        self._events.set_handler(event, func)

    async def disconnect(self) -> None:
        """Close API connections."""
        logger = self._log.getChild("Disconnect")
        self._disconnecting.set()
        if self._api_refresh_task is not None:
            self._api_refresh_task.cancel()
            self._api_refresh_task = None

        # Disconnect MQTT connection
        try:
            if self.mqtt is not None:
                await self.mqtt.adisconnect()
                await self.mqtt.ashutdown()
        except Exception as err:
            logger.debug("Could not disconnect MQTT cleanly: %s", err)
        finally:
            self.mqtt = None
            await self._api.close()

    async def connect(
        self,
    ) -> bool:
        """
        Connect to the cloud service endpoint

        Returns:
            bool: True if connection was successful, otherwise False.
        """
        self._disconnecting = asyncio.Event()
        self._loop = asyncio.get_running_loop()
        self._log.debug("Fetching basic API data")
        await self._fetch()
        self._log.debug("Done fetching basic API data")

        if len(self._mowers) == 0:
            self._log.debug("no mowers connected to account")
            return False

        self._endpoint = self._mowers[0]["mqtt_endpoint"]
        self._user_id = self._mowers[0]["user_id"]

        self._log.debug("Setting up MQTT handler")
        # setup MQTT handler
        self.mqtt = MQTT(
            self._api,
            self._cloud.BRAND_PREFIX,
            self._endpoint,
            self._user_id,
            self._log,
            self._on_update,
            identifier_resolver=self._resolve_mower_identifiers,
            deduplicate_inflight_commands=self._deduplicate_inflight_commands,
            response_timeout=self._command_timeout,
        )

        await self.mqtt.aconnect()

        for mower in self._mowers:
            await self.mqtt.asubscribe(mower["mqtt_topics"]["command_out"], True)

        # Convert time strings to objects.
        for name, device in self.devices.items():
            convert_to_time(
                name, device, device.time_zone, callback=self.update_attribute
            )

        self._log.debug("Connection tasks all done")

        return True

    async def _token_updated(self) -> None:
        """Called when token is updated."""
        if self.mqtt is not None:
            await self.mqtt.aupdate_token()

    @property
    def auth_result(self) -> bool:
        """Return current authentication result."""
        return self._auth_result

    def _on_update(self, payload):  # , topic, payload, dup, qos, retain, **kwargs):
        """Triggered when a MQTT message was received."""
        logger = self._log.getChild("MQTT_data_in")
        try:
            data = json.loads(payload)
            cfg = data.get("cfg", {}) if isinstance(data, dict) else {}
            dat = data.get("dat", {}) if isinstance(data, dict) else {}
            serial = cfg.get("sn")
            uuid = dat.get("uuid")
            mac = dat.get("mac")
            logger.debug(
                "MQTT data received (sn=%s uuid=%s mac=%s)",
                serial,
                uuid,
                mac,
            )

            # "Malformed" message, we are missing a serial number and
            # MAC address to identify the mower.
            if serial is None and uuid is None and mac is None:
                logger.debug("Malformed message received")
                return

            mower = self._match_mower(serial=serial, uuid=uuid, mac=mac)
            if mower is None:
                logger.debug(
                    "Could not match incoming data with a known mower! sn=%s uuid=%s mac=%s",
                    serial,
                    uuid,
                    mac,
                )
                return
            logger.debug("Matched to '%s'", mower["name"])

            device: DeviceHandler = self.devices[mower["name"]]

            if not device.online:
                logger.debug("Device is marked offline - refreshing")
                if self._loop is not None:
                    self._loop.call_soon_threadsafe(
                        lambda: asyncio.create_task(self._fetch())
                    )
                device: DeviceHandler = self.devices[mower["name"]]

            if "raw_data" in mower and mower["raw_data"] == data:
                self._log.debug("Data was already present and not changed.")
                return  # Dataset was not changed, no update needed

            mower["raw_data"] = data
            device: DeviceHandler = self.devices[mower["name"]]
            device.raw_data = data
            logger.debug("MQTT data refreshed for mower '%s'", mower["name"])

            self._events.call(
                LandroidEvent.DATA_RECEIVED, name=mower["name"], device=device
            )
        except json.decoder.JSONDecodeError:
            logger.debug("Malformed MQTT message received")

    def _match_mower(
        self, serial: str | None = None, uuid: str | None = None, mac: str | None = None
    ) -> dict[str, Any] | None:
        """Return mower by prioritized identifier matching."""
        if serial is not None:
            mower = self._mowers_by_serial.get(serial)
            if mower is not None:
                return mower
        if uuid is not None:
            mower = self._mowers_by_uuid.get(uuid)
            if mower is not None:
                return mower
        if mac is not None:
            mower = self._mowers_by_mac.get(mac)
            if mower is not None:
                return mower
        return None

    def _rebuild_mower_indices(self) -> None:
        """Rebuild mower lookup dictionaries for fast identifier matching."""
        by_serial: dict[str, dict[str, Any]] = {}
        by_uuid: dict[str, dict[str, Any]] = {}
        by_mac: dict[str, dict[str, Any]] = {}
        for mower in self._mowers or []:
            serial = mower.get("serial_number")
            if serial is not None:
                by_serial[str(serial)] = mower

            uuid = mower.get("uuid")
            if uuid is not None:
                by_uuid[str(uuid)] = mower

            mac = mower.get("mac_address")
            if mac is not None and mac != "__UUID__":
                by_mac[str(mac)] = mower

        # Swap references atomically so callback readers never observe partial updates.
        self._mowers_by_serial = by_serial
        self._mowers_by_uuid = by_uuid
        self._mowers_by_mac = by_mac

    def _resolve_mower_identifiers(self, identifier: str) -> set[str]:
        """Return equivalent mower identifiers for serial/uuid/mac matching."""
        mower = (
            self._mowers_by_serial.get(identifier)
            or self._mowers_by_uuid.get(identifier)
            or self._mowers_by_mac.get(identifier)
        )
        if mower is None:
            return {identifier}

        identifiers = {
            (
                str(mower.get("serial_number"))
                if mower.get("serial_number") is not None
                else None
            ),
            str(mower.get("uuid")) if mower.get("uuid") is not None else None,
            (
                str(mower.get("mac_address"))
                if mower.get("mac_address") is not None
                else None
            ),
        }
        identifiers.discard(None)
        identifiers.discard("__UUID__")
        return identifiers if identifiers else {identifier}

    def _on_api_update(self, data):  # , topic, payload, dup, qos, retain, **kwargs):
        """Triggered when API has been updated."""
        logger = self._log.getChild("API_update")
        try:
            self._events.call(LandroidEvent.API, api_data=data)
        except json.decoder.JSONDecodeError:
            logger.debug("Malformed MQTT message received")

    async def _fetch(self, forced: bool = False) -> None:
        """Fetch base API information."""
        logger = self._log.getChild("API_Fetch")
        if self._disconnecting.is_set():
            return

        try:
            self._mowers = await self._api.get_mowers()
        except NoConnectionError as err:
            if forced:
                await self._schedule_api_refresh(True)
                return
            else:
                raise NoConnectionError() from err
        except InternalServerError:
            if forced:
                await self._schedule_api_refresh(True)

            return

        if self._disconnecting.is_set():
            return

        # self.devices = {}
        for mower in self._mowers:
            try:
                device = DeviceHandler(self._api, mower, self._tz, False)
                if not isinstance(mower["last_status"], type(None)):
                    device.raw_data = mower["last_status"]["payload"]

                _LOGGER.debug("Mower '%s' data: %s", mower["name"], mower)
                self.devices.update({mower["name"]: device})

                if isinstance(mower["mac_address"], type(None)):
                    mower["mac_address"] = (
                        device.raw_data["dat"]["mac"]
                        if "mac" in device.raw_data["dat"]
                        else "__UUID__"
                    )

                logger.debug("API data refreshed for mower '%s'", mower["name"])
                self._events.call(LandroidEvent.API, name=mower["name"], device=device)
            except TypeError:
                pass

        self._rebuild_mower_indices()

        await self._schedule_api_refresh()

    async def _schedule_api_refresh(self, is_err: bool = False) -> None:
        """Schedule the API refresh."""
        logger = self._log.getChild("API_Refresh_Scheduler")
        if self._disconnecting.is_set():
            return
        if self._api_refresh_task is not None:
            self._api_refresh_task.cancel()

        if is_err:
            refresh_secs = 5 * 60
        else:
            refresh_secs = randint(API_REFRESH_TIME_MIN, API_REFRESH_TIME_MAX) * 60

        timezone = (
            ZoneInfo(self._tz)
            if not isinstance(self._tz, type(None))
            else ZoneInfo("UTC")
        )
        now = datetime.now().astimezone(timezone)
        next_api_refresh = now + timedelta(seconds=refresh_secs)
        logger.debug(
            "Scheduling an API refresh at %s",
            next_api_refresh,
        )

        async def _refresh_later() -> None:
            try:
                await asyncio.sleep(refresh_secs)
                await self._fetch(True)
            except asyncio.CancelledError:
                return

        self._api_refresh_task = asyncio.create_task(_refresh_later())

    def get_mower(self, serial_number: str, device: bool = False) -> dict:
        """Get a specific mower object.

        Args:
            serial_number (str): Serial number of the device
        """

        if device:
            for mower in self.devices.items():
                if mower[1].serial_number == serial_number:
                    return mower[1]
        else:
            mower = self._mowers_by_serial.get(serial_number)
            if mower is not None:
                return mower

        raise MowerNotFoundError(
            f"Mower with serialnumber {serial_number} was not found."
        )

    async def update(self, serial_number: str) -> None:
        """Request a state refresh."""
        mower = self.get_mower(serial_number)
        _LOGGER.debug("Trying to refresh '%s'", serial_number)

        try:
            await self.mqtt.aping(
                serial_number if mower["protocol"] == 0 else mower["uuid"],
                mower["mqtt_topics"]["command_in"],
                mower["protocol"],
            )
        except NoConnectionError:
            raise NoConnectionError from None

    async def start(self, serial_number: str) -> None:
        """Start mowing task

        Args:
            serial_number (str): Serial number of the device

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            _LOGGER.debug("Sending start command to '%s'", serial_number)
            await self.mqtt.acommand(
                serial_number if mower["protocol"] == 0 else mower["uuid"],
                mower["mqtt_topics"]["command_in"],
                Command.START,
                mower["protocol"],
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    async def home(self, serial_number: str) -> None:
        """Stop the current task and go home.
        If the knifes was turned on when this is called,
        it will return home with knifes still turned on.

        Args:
            serial_number (str): Serial number of the device

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)

        if mower["online"]:
            await self.mqtt.acommand(
                serial_number if mower["protocol"] == 0 else mower["uuid"],
                mower["mqtt_topics"]["command_in"],
                Command.HOME,
                mower["protocol"],
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    async def safehome(self, serial_number: str) -> None:
        """Stop and go home with the blades off

        Args:
            serial_number (str): Serial number of the device

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            await self.mqtt.acommand(
                serial_number if mower["protocol"] == 0 else mower["uuid"],
                mower["mqtt_topics"]["command_in"],
                Command.SAFEHOME,
                mower["protocol"],
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    async def pause(self, serial_number: str) -> None:
        """Pause the mowing task

        Args:
            serial_number (str): Serial number of the device

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            await self.mqtt.acommand(
                serial_number if mower["protocol"] == 0 else mower["uuid"],
                mower["mqtt_topics"]["command_in"],
                Command.PAUSE,
                mower["protocol"],
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    async def raindelay(self, serial_number: str, rain_delay: str) -> None:
        """Set new rain delay.

        Args:
            serial_number (str): Serial number of the device
            rain_delay (str): Rain delay in minutes.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            if not isinstance(rain_delay, int):
                rain_delay = int(rain_delay)
            await self.mqtt.apublish(
                serial_number if mower["protocol"] == 0 else mower["uuid"],
                mower["mqtt_topics"]["command_in"],
                {"rd": rain_delay},
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    async def set_lock(self, serial_number: str, state: bool) -> None:
        """Set the device locked state.

        Args:
            serial_number (str): Serial number of the device
            state (bool): True will lock the device, False will unlock the device.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            await self.mqtt.acommand(
                serial_number if mower["protocol"] == 0 else mower["uuid"],
                mower["mqtt_topics"]["command_in"],
                Command.LOCK if state else Command.UNLOCK,
                mower["protocol"],
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    async def set_partymode(self, serial_number: str, state: bool) -> None:
        """Turn on or off the partymode.

        Args:
            serial_number (str): Serial number of the device
            state (bool): True is enabling partymode, False is disabling partymode.

        Raises:
            NoPartymodeError: Raised if the device does not support partymode.
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)

        if mower["online"]:
            device = DeviceHandler(self._api, mower, self._tz)
            if device.capabilities.check(DeviceCapability.PARTY_MODE):
                if mower["protocol"] == 0:
                    await self.mqtt.apublish(
                        serial_number if mower["protocol"] == 0 else mower["uuid"],
                        mower["mqtt_topics"]["command_in"],
                        (
                            {"sc": {"m": 2, "distm": 0}}
                            if state
                            else {"sc": {"m": 1, "distm": 0}}
                        ),
                        mower["protocol"],
                    )
                else:
                    await self.mqtt.apublish(
                        serial_number if mower["protocol"] == 0 else mower["uuid"],
                        mower["mqtt_topics"]["command_in"],
                        {"sc": {"enabled": 0}} if state else {"sc": {"enabled": 1}},
                        mower["protocol"],
                    )
            elif not device.capabilities.check(DeviceCapability.PARTY_MODE):
                raise NoPartymodeError("This device does not support Partymode")
        elif not mower["online"]:
            raise OfflineError("The device is currently offline, no action was sent.")

    async def set_offlimits(self, serial_number: str, state: bool) -> None:
        """Turn on or off the off limits module.

        Args:
            serial_number (str): Serial number of the device
            state (bool): True is enabling off limits module, False is disabling off limits module.

        Raises:
            NoOfflimitsError: Raised if the device does not support off limits.
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)

        if mower["online"]:
            _LOGGER.debug("Setting offlimits")
            device = DeviceHandler(self._api, mower, self._tz)
            if device.capabilities.check(DeviceCapability.OFF_LIMITS):
                await self.mqtt.apublish(
                    serial_number if device.protocol == 0 else device.uuid,
                    mower["mqtt_topics"]["command_in"],
                    (
                        {
                            "modules": {
                                "DF": {
                                    "cut": 1,
                                    "fh": 1 if device.offlimit_shortcut else 0,
                                }
                            }
                        }
                        if state
                        else {
                            "modules": {
                                "DF": {
                                    "cut": 0,
                                    "fh": 1 if device.offlimit_shortcut else 0,
                                }
                            }
                        }
                    ),
                    device.protocol,
                )
            elif not device.capabilities.check(DeviceCapability.OFF_LIMITS):
                raise NoOfflimitsError("This device does not support Off Limits")
        elif not mower["online"]:
            raise OfflineError("The device is currently offline, no action was sent.")

    async def set_offlimits_shortcut(self, serial_number: str, state: bool) -> None:
        """Turn on or off the off limits shortcut function.

        Args:
            serial_number (str): Serial number of the device
            state (bool): True is enabling shortcut, False is disabling shortcut.

        Raises:
            NoOfflimitsError: Raised if the device does not support off limits.
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)

        if mower["online"]:
            _LOGGER.debug("Setting offlimits")
            device = DeviceHandler(self._api, mower, self._tz)
            if device.capabilities.check(DeviceCapability.OFF_LIMITS):
                await self.mqtt.apublish(
                    serial_number if device.protocol == 0 else device.uuid,
                    mower["mqtt_topics"]["command_in"],
                    (
                        {
                            "modules": {
                                "DF": {
                                    "cut": 1 if device.offlimit else 0,
                                    "fh": 1,
                                }
                            }
                        }
                        if state
                        else {
                            "modules": {
                                "DF": {
                                    "cut": 1 if device.offlimit else 0,
                                    "fh": 0,
                                }
                            }
                        }
                    ),
                    device.protocol,
                )
            elif not device.capabilities.check(DeviceCapability.OFF_LIMITS):
                raise NoOfflimitsError("This device does not support Off Limits")
        elif not mower["online"]:
            raise OfflineError("The device is currently offline, no action was sent.")

    async def setzone(self, serial_number: str, zone: str | int) -> None:
        """Set zone to be mowed when next mowing task is started.

        Args:
            serial_number (str): Serial number of the device
            zone (str | int): Zone to mow, valid possibilities are a number from 1 to 4.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            device = DeviceHandler(self._api, mower, self._tz)
            if not isinstance(zone, int):
                zone = int(zone)

            if (
                zone >= len(device.zone["starting_point"])
                or device.zone["starting_point"][zone] == 0
            ):
                raise ZoneNotDefined(
                    f"Cannot request zone {zone} as it is not defined."
                )

            if not zone in device.zone["indicies"]:
                raise ZoneNoProbability(
                    f"Cannot request zone {zone} as it has no probability set."
                )

            current_zones = device.zone["indicies"]
            requested_zone_index = current_zones.index(zone)
            next_zone_index = device.zone["index"]

            no_indices = len(current_zones)
            offset = (requested_zone_index - next_zone_index) % no_indices
            new_zones = []
            for i in range(0, no_indices):
                new_zones.append(current_zones[(offset + i) % no_indices])

            device = DeviceHandler(self._api, mower, self._tz)
            await self.mqtt.apublish(
                serial_number if mower["protocol"] == 0 else mower["uuid"],
                mower["mqtt_topics"]["command_in"],
                {"mzv": new_zones},
                mower["protocol"],
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    async def zonetraining(self, serial_number: str) -> None:
        """Start the zone training task.

        Args:
            serial_number (str): Serial number of the device

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            _LOGGER.debug("Sending ZONETRAINING command to %s", mower["name"])
            await self.mqtt.acommand(
                serial_number if mower["protocol"] == 0 else mower["uuid"],
                mower["mqtt_topics"]["command_in"],
                Command.ZONETRAINING,
                mower["protocol"],
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    async def restart(self, serial_number: str):
        """Reboot the device baseboard.

        Args:
            serial_number (str): Serial number of the device

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            _LOGGER.debug("Sending RESTART command to %s", mower["name"])
            await self.mqtt.acommand(
                serial_number if mower["protocol"] == 0 else mower["uuid"],
                mower["mqtt_topics"]["command_in"],
                Command.RESTART,
                mower["protocol"],
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    async def toggle_schedule(self, serial_number: str, enable: bool) -> None:
        """Turn on or off the schedule.

        Args:
            serial_number (str): Serial number of the device
            enable (bool): True is enabling the schedule, Fasle is disabling the schedule.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            await self.mqtt.apublish(
                serial_number if mower["protocol"] == 0 else mower["uuid"],
                mower["mqtt_topics"]["command_in"],
                {"sc": {"m": 1}} if enable else {"sc": {"m": 0}},
                mower["protocol"],
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    async def edgecut(self, serial_number: str) -> None:
        """Start an edge cutting task.

        Args:
            serial_number (str): Serial number of the device
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            device = DeviceHandler(self._api, mower, self._tz)
            if device.capabilities.check(DeviceCapability.EDGE_CUT):
                if mower["protocol"] == 0:
                    await self.mqtt.apublish(
                        serial_number,
                        mower["mqtt_topics"]["command_in"],
                        {"sc": {"ots": {"bc": 1, "wtm": 0}}},
                        mower["protocol"],
                    )
                else:
                    await self.mqtt.apublish(
                        mower["uuid"],
                        mower["mqtt_topics"]["command_in"],
                        {"cmd": 101},
                        mower["protocol"],
                    )

    async def ots(self, serial_number: str, boundary: bool, runtime: str) -> None:
        """Start a One-Time-Schedule task

        Args:
            serial_number (str): Serial number of the device
            boundary (bool): If True the device will start the task cutting the edge.
            runtime (str | int): Minutes to run the task before returning to dock.

        Raises:
            NoOneTimeScheduleError: OTS is not supported by the device.
            OfflineError: Raised when the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            device = DeviceHandler(self._api, mower, self._tz)
            if device.capabilities.check(DeviceCapability.ONE_TIME_SCHEDULE):
                if not isinstance(runtime, int):
                    runtime = int(runtime)

                device = DeviceHandler(self._api, mower, self._tz)
                if mower["protocol"] == 0:
                    await self.mqtt.apublish(
                        serial_number,
                        mower["mqtt_topics"]["command_in"],
                        {"sc": {"ots": {"bc": int(boundary), "wtm": runtime}}},
                        mower["protocol"],
                    )
                else:
                    await self.mqtt.apublish(
                        mower["uuid"],
                        mower["mqtt_topics"]["command_in"],
                        {
                            "cmd": 10,
                            "sc": {
                                "once": {
                                    "cfg": {"cut": {"b": int(boundary), "z": []}},
                                    "time": (runtime),
                                }
                            },
                        },
                        mower["protocol"],
                    )
            elif not device.capabilities.check(DeviceCapability.ONE_TIME_SCHEDULE):
                raise NoOneTimeScheduleError(
                    "This device does not support Edgecut-on-demand"
                )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    async def send(self, serial_number: str, data: str) -> None:
        """Send raw JSON data to the device.

        Args:
            serial_number (str): Serial number of the device
            data (str): Data to be sent, formatted as a valid JSON object.

        Raises:
            OfflineError: Raised if the device isn't online.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            _LOGGER.debug("Sending %s to %s", data, mower["name"])
            await self.mqtt.apublish(
                serial_number if mower["protocol"] == 0 else mower["uuid"],
                mower["mqtt_topics"]["command_in"],
                json.loads(data),
                mower["protocol"],
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    async def reset_charge_cycle_counter(self, serial_number: str) -> None:
        """Resets charge cycle counter.

        Args:
            serial_number (str): Serial number of the device
            data (str): Data to be sent, formatted as a valid JSON object.

        Raises:
            OfflineError: Raised if the device isn't online.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            _LOGGER.debug("Resetting charge cycle counter for %s", mower["name"])
            await self._api.check_token()
            await APOST(
                f"https://{self._api.cloud.ENDPOINT}/api/v2/product-items/{serial_number}/counters/battery/reset",
                "",
                HEADERS(self._api.access_token),
                session=await self._api._ensure_session(),
            )
            await self._fetch(True)

    async def reset_blade_counter(self, serial_number: str) -> None:
        """Resets blade counter.

        Args:
            serial_number (str): Serial number of the device
            data (str): Data to be sent, formatted as a valid JSON object.

        Raises:
            OfflineError: Raised if the device isn't online.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            _LOGGER.debug("Resetting blade counter for %s", mower["name"])
            await self._api.check_token()
            await APOST(
                f"https://{self._api.cloud.ENDPOINT}/api/v2/product-items/{serial_number}/counters/blade/reset",
                "",
                HEADERS(self._api.access_token),
                session=await self._api._ensure_session(),
            )
            await self._fetch(True)

    def get_cutting_height(self, serial_number: str) -> int:
        """Get the current cutting height of the device.

        Args:
            serial_number (str): Serial number of the device

        Returns:
            int: Cutting height in mm

        Raises:
            NoCuttingHeightError: Raised if the device does not support cutting height.
        """
        mower = self.get_mower(serial_number)
        try:
            return int(mower["last_status"]["payload"]["cfg"]["modules"]["EA"]["h"])
        except KeyError:
            raise NoCuttingHeightError("This device does not support cutting height")

    async def set_cutting_height(self, serial_number: str, height: int) -> None:
        """Set the cutting height of the device.

        Args:
            serial_number (str): Serial number of the device
            height (int): Cutting height in mm

        Raises:
            NoCuttingHeightError: Raised if the device does not support cutting height.
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            device = DeviceHandler(self._api, mower, self._tz)
            if device.capabilities.check(DeviceCapability.CUTTING_HEIGHT):
                await self.mqtt.apublish(
                    serial_number if mower["protocol"] == 0 else mower["uuid"],
                    mower["mqtt_topics"]["command_in"],
                    {"cmd": 0, "modules": {"EA": {"h": height}}},
                    mower["protocol"],
                )
            else:
                raise NoCuttingHeightError(
                    "This device does not support cutting height"
                )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    async def set_acs(self, serial_number: str, state: bool) -> None:
        """Enable or disable the ACS module.

        Args:
            serial_number (str): Serial number of the device
            state (bool): True is enabling ACS, False is disabling ACS.

        Raises:
            NoACSModuleError: Raised if the device does not support ACS.
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            device = DeviceHandler(self._api, mower, self._tz)
            if device.capabilities.check(DeviceCapability.ACS):
                await self.mqtt.apublish(
                    serial_number if mower["protocol"] == 0 else mower["uuid"],
                    mower["mqtt_topics"]["command_in"],
                    {"cmd": 0, "modules": {"US": {"enabled": 1 if state else 0}}},
                    mower["protocol"],
                )
            else:
                raise NoACSModuleError(
                    "This device does not have an ACS module installed."
                )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")
