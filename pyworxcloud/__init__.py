"""pyWorxCloud definition."""

# pylint: disable=undefined-loop-variable
# pylint: disable=line-too-long
# pylint: disable=too-many-lines
from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
import warnings
from datetime import datetime, timedelta, timezone
from random import randint
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
    NoFirmwareAvailableError,
    NoFirmwareOtaError,
    NoOfflimitsError,
    NoOneTimeScheduleError,
)
from .exceptions import NoPartymodeError as NoPartymodeError
from .exceptions import NoPauseModeError as NoPauseModeError
from .exceptions import (
    NotFoundError,
    OfflineError,
    RequestError,
    TooManyRequestsError,
    ZoneNoProbability,
    ZoneNotDefined,
)
from .helpers import convert_to_time, get_logger, redact_email_address
from .utils import MQTT, DeviceCapability, DeviceHandler, ScheduleEntry, ScheduleModel
from .utils.lawn import Lawn
from .utils.mqtt import Command
from .utils.requests import AGET, APOST, APUT, HEADERS
from .utils.schedule_codec import add_schedule_entry as add_schedule_entry_model
from .utils.schedule_codec import delete_schedule_entry as delete_schedule_entry_model
from .utils.schedule_codec import (
    schedule_model_from_payload,
    schedule_payload_from_model,
)
from .utils.schedule_codec import update_schedule_entry as update_schedule_entry_model
from .utils.schedule_codec import validate_schedule_model

if sys.version_info < (3, 9, 0):
    sys.exit("The pyWorxcloud module requires Python 3.9.0 or later")

_LOGGER = logging.getLogger(__name__)

API_REFRESH_TIME_MIN = 5
API_REFRESH_TIME_MAX = 10
DEFAULT_COMMAND_TIMEOUT = 30.0
VISION_BORDER_DISTANCE_MM_VALUES = (50, 100, 150, 200)


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
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "Sync 'with WorxCloud(...)' cannot be used inside a running event loop. "
                "Use 'async with WorxCloud(...)' instead."
            )

        warnings.warn(
            "Sync context manager support is deprecated and will be removed in a future release. "
            "Use 'async with WorxCloud(...)' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
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
        redacted_username = redact_email_address(self._username)
        self._log.debug("Authenticating %s", redacted_username)

        try:
            await self._api.get_token()
        except TooManyRequestsError:
            raise TooManyRequestsError from None

        auth = self._api.authenticate()
        if auth is False:
            self._auth_result = False
            self._log.debug("Authentication for %s failed!", redacted_username)
            raise AuthorizationError("Unauthorized")

        self._auth_result = True
        self._log.debug("Authentication for %s successful", redacted_username)

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
                disconnect_failed = False
                try:
                    started = time.perf_counter()
                    await self.mqtt.adisconnect()
                    logger.debug(
                        "MQTT adisconnect completed in %.3fs",
                        time.perf_counter() - started,
                    )
                except Exception as err:
                    disconnect_failed = True
                    logger.debug("Could not disconnect MQTT cleanly: %s", err)

                try:
                    started = time.perf_counter()
                    await self.mqtt.ashutdown()
                    logger.debug(
                        "MQTT ashutdown completed in %.3fs",
                        time.perf_counter() - started,
                    )
                except Exception as err:
                    logger.debug("Could not shutdown MQTT cleanly: %s", err)
                    if not disconnect_failed:
                        raise
        finally:
            self.mqtt = None
            started = time.perf_counter()
            await self._api.close()
            logger.debug("API close completed in %.3fs", time.perf_counter() - started)

    async def connect(
        self,
    ) -> bool:
        """
        Connect to the cloud service endpoint

        Returns:
            bool: True if connection was successful, otherwise False.
        """
        logger = self._log.getChild("Connect")
        self._disconnecting = asyncio.Event()
        self._loop = asyncio.get_running_loop()
        try:
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
            self.mqtt = await asyncio.to_thread(
                MQTT,
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
        except Exception:
            logger.debug(
                "Connect failed; cleaning up partial resources",
                exc_info=True,
            )
            try:
                await self.disconnect()
            except Exception:
                logger.debug(
                    "Cleanup after failed connect raised",
                    exc_info=True,
                )
            raise

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
                self._log.debug(
                    "MQTT data received for mower '%s' but payload is unchanged.",
                    mower["name"],
                )
                # Still emit event so listeners can refresh timestamps/UI heartbeat.
                self._events.call(
                    LandroidEvent.DATA_RECEIVED, name=mower["name"], device=device
                )
                return

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
                previous_device = self.devices.get(mower["name"])
                device = DeviceHandler(self._api, mower, self._tz, False)
                if not isinstance(mower["last_status"], type(None)):
                    device.raw_data = mower["last_status"]["payload"]

                if (
                    previous_device is not None
                    and getattr(device, "updated_origin", None) == "observed"
                    and isinstance(getattr(previous_device, "updated", None), datetime)
                ):
                    device.updated = previous_device.updated
                    device.updated_origin = getattr(
                        previous_device, "updated_origin", "existing"
                    )
                    mower["last_status"]["timestamp"] = previous_device.updated

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

        try:
            timezone_info = (
                ZoneInfo(self._tz)
                if not isinstance(self._tz, type(None))
                else timezone.utc
            )
        except ZoneInfoNotFoundError:
            timezone_info = timezone.utc
        now = datetime.now().astimezone(timezone_info)
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

    @staticmethod
    def _require_bool(value: Any, name: str) -> bool:
        """Require a strict bool input value."""
        if not isinstance(value, bool):
            raise ValueError(f"{name} must be a boolean value")
        return value

    @staticmethod
    def _coerce_int(
        value: Any,
        name: str,
        minimum: int | None = None,
        maximum: int | None = None,
    ) -> int:
        """Coerce an integer-like input and optionally enforce bounds."""
        if isinstance(value, bool):
            raise ValueError(f"{name} must be an integer value")
        try:
            parsed = int(value)
        except (TypeError, ValueError) as err:
            raise ValueError(f"{name} must be an integer value") from err
        if minimum is not None and parsed < minimum:
            raise ValueError(f"{name} must be greater than or equal to {minimum}")
        if maximum is not None and parsed > maximum:
            raise ValueError(f"{name} must be less than or equal to {maximum}")
        return parsed

    @staticmethod
    def _require_step(value: int, name: str, step: int) -> int:
        """Require that an integer value follows the documented step size."""
        if value % step != 0:
            raise ValueError(f"{name} must be in steps of {step}")
        return value

    @staticmethod
    def _deep_merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        """Merge nested dictionaries without mutating the inputs."""
        merged = json.loads(json.dumps(base))
        for key, value in patch.items():
            if (
                key in merged
                and isinstance(merged[key], dict)
                and isinstance(value, dict)
            ):
                merged[key] = WorxCloud._deep_merge_dict(merged[key], value)
            else:
                merged[key] = value
        return merged

    @staticmethod
    def _clone_dict(value: dict[str, Any] | None) -> dict[str, Any]:
        """Return a JSON-safe deep copy."""
        return json.loads(json.dumps(value)) if isinstance(value, dict) else {}

    @staticmethod
    def _normalize_auto_schedule_exclusion_days_for_write(
        days: Any,
    ) -> list[dict[str, Any]]:
        """Return a stable seven-day exclusion scheduler structure."""
        raw_days = days if isinstance(days, list) else []
        normalized_days = []
        for day_index in range(7):
            day_entry = raw_days[day_index] if day_index < len(raw_days) else {}
            day = day_entry if isinstance(day_entry, dict) else {}
            raw_slots = day.get("slots", [])
            slots = raw_slots if isinstance(raw_slots, list) else []
            normalized_days.append(
                {
                    "exclude_day": bool(day.get("exclude_day", False)),
                    "slots": [slot for slot in slots if isinstance(slot, dict)],
                }
            )
        return normalized_days

    def _normalize_auto_schedule_exclusion_slots_for_write(
        self, slots: Any
    ) -> list[dict[str, Any]]:
        """Validate and normalize exclusion slots for write operations."""
        if not isinstance(slots, list):
            raise ValueError("slots must be a list of exclusion slot objects")

        normalized_slots = []
        for index, slot in enumerate(slots):
            if not isinstance(slot, dict):
                raise ValueError(
                    f"slots[{index}] must be a dictionary with slot values"
                )
            reason = slot.get("reason", "generic")
            if not isinstance(reason, str):
                raise ValueError(f"slots[{index}].reason must be a string value")
            reason = reason.strip()
            if reason not in {"generic", "irrigation"}:
                raise ValueError(
                    f"slots[{index}].reason must be one of generic or irrigation"
                )
            normalized_slots.append(
                {
                    "start_time": self._coerce_int(
                        slot.get("start_time"),
                        f"slots[{index}].start_time",
                        minimum=0,
                        maximum=1439,
                    ),
                    "duration": self._coerce_int(
                        slot.get("duration"),
                        f"slots[{index}].duration",
                        minimum=0,
                        maximum=1440,
                    ),
                    "reason": reason,
                }
            )

        return normalized_slots

    @staticmethod
    def _firmware_changelog_to_markdown(changelog: Any) -> Any:
        """Convert firmware changelog text into a Markdown-friendly structure."""
        if isinstance(changelog, dict):
            normalized: dict[str, str] = {}
            for language, text in changelog.items():
                if not isinstance(text, str):
                    continue
                markdown = WorxCloud._firmware_changelog_text_to_markdown(text)
                if markdown:
                    normalized[str(language)] = markdown
            return normalized or None

        if isinstance(changelog, str):
            return WorxCloud._firmware_changelog_text_to_markdown(changelog)

        return None

    @staticmethod
    def _firmware_changelog_text_to_markdown(text: str) -> str | None:
        """Normalize a single changelog string into readable Markdown."""
        stripped = text.strip()
        if not stripped:
            return None

        lines = []
        for raw_line in stripped.splitlines():
            line = raw_line.strip()
            if not line:
                lines.append("")
                continue

            if line.startswith("• "):
                lines.append(f"- {line[2:].strip()}")
                continue
            if line.startswith("* "):
                lines.append(f"- {line[2:].strip()}")
                continue

            lines.append(line)

        markdown_lines: list[str] = []
        previous_blank = False
        for line in lines:
            if not line:
                if not previous_blank and markdown_lines:
                    markdown_lines.append("")
                previous_blank = True
                continue
            markdown_lines.append(line)
            previous_blank = False

        markdown = "\n".join(markdown_lines).strip()
        return markdown or None

    @staticmethod
    def _normalize_firmware_info_entry(entry: Any) -> dict[str, Any] | None:
        """Return a normalized firmware info entry from the app-observed payload."""
        if not isinstance(entry, dict):
            return None

        version = entry.get("version")
        if not isinstance(version, str) or not version.strip():
            return None

        normalized = {
            "uuid": entry.get("uuid"),
            "version": version.strip(),
            "released_at": entry.get("releasedAt"),
            "changelog": entry.get("changelog"),
            "changelog_markdown": WorxCloud._firmware_changelog_to_markdown(
                entry.get("changelog")
            ),
        }
        return normalized

    def _cache_firmware_upgrade_info(
        self, mower: dict[str, Any], normalized: dict[str, Any]
    ) -> None:
        """Keep cached mower/device firmware upgrade data aligned."""
        mower["firmware_upgrade"] = self._clone_dict(normalized)
        device = self.devices.get(mower["name"])
        if device is None or not isinstance(getattr(device, "firmware", None), dict):
            return

        device.firmware["upgrade"] = self._clone_dict(normalized)
        device.firmware["latest_version"] = normalized.get("latest_version")
        device.firmware["update_available"] = normalized.get("update_available")
        device.firmware["ota_supported"] = normalized.get("ota_supported")
        device.firmware["mandatory"] = normalized.get("mandatory")
        device.firmware["upgrade_failed"] = normalized.get("upgrade_failed")

    @staticmethod
    def _firmware_ota_supported(
        mower: dict[str, Any], device: Any | None = None
    ) -> bool | None:
        """Return whether OTA firmware updates appear to be supported."""
        firmware_upgrade = mower.get("firmware_upgrade")
        if isinstance(firmware_upgrade, dict):
            ota_supported = firmware_upgrade.get("ota_supported")
            if isinstance(ota_supported, bool):
                return ota_supported

        capabilities = mower.get("capabilities")
        if isinstance(capabilities, list):
            return "ota_upgrade" in capabilities

        api_capabilities = getattr(device, "api_capabilities", None)
        if isinstance(api_capabilities, list):
            return "ota_upgrade" in api_capabilities

        return None

    async def _put_auto_schedule_settings_patch(
        self, serial_number: str, patch: dict[str, Any]
    ) -> None:
        """PUT a merged top-level auto-schedule settings patch."""
        mower = self.get_mower(serial_number)
        current_settings = self._clone_dict(mower.get("auto_schedule_settings"))
        payload = {
            "auto_schedule_settings": self._deep_merge_dict(current_settings, patch)
        }

        await self._api.check_token()
        response = await APUT(
            f"https://{self._api.cloud.ENDPOINT}/api/v2/product-items/{serial_number}",
            payload,
            HEADERS(self._api.access_token),
            session=await self._api._ensure_session(),
        )

        if isinstance(response, dict):
            mower.update(response)

        mower["auto_schedule_settings"] = payload["auto_schedule_settings"]
        device = self.devices.get(mower["name"])
        if device is not None:
            auto_schedule = device.schedules.get("auto_schedule")
            if isinstance(auto_schedule, dict):
                settings = auto_schedule.get("settings")
                if isinstance(settings, dict):
                    auto_schedule["settings"] = self._deep_merge_dict(
                        self._clone_dict(settings), patch
                    )

        await self._fetch(True)

    def _get_current_schedule_payload(self, mower: dict[str, Any]) -> dict[str, Any]:
        """Return the latest raw schedule payload for a mower."""
        last_status = mower.get("last_status")
        if isinstance(last_status, dict):
            payload = last_status.get("payload")
            if isinstance(payload, dict):
                cfg = payload.get("cfg")
                if isinstance(cfg, dict):
                    sc = cfg.get("sc")
                    if isinstance(sc, dict):
                        return self._clone_dict(sc)
        return {}

    def _get_current_cfg_payload(self, mower: dict[str, Any]) -> dict[str, Any]:
        """Return the latest raw cfg payload for a mower."""
        last_status = mower.get("last_status")
        if isinstance(last_status, dict):
            payload = last_status.get("payload")
            if isinstance(payload, dict):
                cfg = payload.get("cfg")
                if isinstance(cfg, dict):
                    return self._clone_dict(cfg)
        return {}

    def _build_border_cut_settings_payload(
        self,
        *,
        cut_over_border: bool | None = None,
        border_distance: int | None = None,
    ) -> dict[str, Any]:
        """Build the observed protocol 1 cut payload for border-cut settings."""
        cut_payload: dict[str, int] = {}
        if cut_over_border is not None:
            cut_payload["ob"] = int(cut_over_border)
        if border_distance is not None:
            cut_payload["bd"] = int(border_distance)

        if not cut_payload:
            raise ValueError("Unable to determine border-cut settings payload")

        return cut_payload

    def _build_schedule_model(self, mower: dict[str, Any]) -> ScheduleModel:
        """Build a normalized schedule model from the mower cache."""
        return schedule_model_from_payload(
            mower["protocol"], self._get_current_schedule_payload(mower)
        )

    def get_schedule(self, serial_number: str) -> ScheduleModel:
        """Return the normalized schedule model for a mower."""
        mower = self.get_mower(serial_number)
        return self._build_schedule_model(mower)

    async def _publish_schedule_payload(
        self, mower: dict[str, Any], sc_payload: dict[str, Any]
    ) -> None:
        """Publish a full schedule payload and update the local cache."""
        if not mower["online"]:
            raise OfflineError("The device is currently offline, no action was sent.")

        identifier = mower["serial_number"] if mower["protocol"] == 0 else mower["uuid"]
        await self.mqtt.apublish(
            identifier,
            mower["mqtt_topics"]["command_in"],
            {"sc": sc_payload},
            mower["protocol"],
        )

        last_status = mower.get("last_status")
        if isinstance(last_status, dict):
            payload = last_status.get("payload")
            if isinstance(payload, dict):
                cfg = payload.setdefault("cfg", {})
                if isinstance(cfg, dict):
                    cfg["sc"] = self._clone_dict(sc_payload)
                    device = self.devices.get(mower["name"])
                    if device is not None:
                        device.raw_data = json.dumps(payload)

        await self._schedule_api_refresh()

    async def set_schedule(self, serial_number: str, schedule: ScheduleModel) -> None:
        """Persist a normalized schedule model to the mower."""
        mower = self.get_mower(serial_number)
        schedule = validate_schedule_model(schedule)
        if schedule.protocol != mower["protocol"]:
            raise ValueError("schedule protocol does not match mower protocol")

        current_payload = self._get_current_schedule_payload(mower)
        sc_payload = schedule_payload_from_model(schedule, current_payload)
        await self._publish_schedule_payload(mower, sc_payload)

    async def add_schedule_entry(
        self, serial_number: str, entry: ScheduleEntry
    ) -> None:
        """Add one normalized schedule entry."""
        mower = self.get_mower(serial_number)
        schedule = add_schedule_entry_model(self._build_schedule_model(mower), entry)
        await self.set_schedule(serial_number, schedule)

    async def update_schedule_entry(
        self, serial_number: str, entry_id: str, entry: ScheduleEntry
    ) -> None:
        """Update one normalized schedule entry."""
        mower = self.get_mower(serial_number)
        schedule = update_schedule_entry_model(
            self._build_schedule_model(mower), entry_id, entry
        )
        await self.set_schedule(serial_number, schedule)

    async def delete_schedule_entry(self, serial_number: str, entry_id: str) -> None:
        """Delete one normalized schedule entry."""
        mower = self.get_mower(serial_number)
        schedule = delete_schedule_entry_model(
            self._build_schedule_model(mower), entry_id
        )
        await self.set_schedule(serial_number, schedule)

    async def update(self, serial_number: str, timeout: float | None = None) -> None:
        """Request a state refresh."""
        mower = self.get_mower(serial_number)
        _LOGGER.debug("Trying to refresh '%s'", serial_number)

        try:
            await self.mqtt.aping(
                serial_number if mower["protocol"] == 0 else mower["uuid"],
                mower["mqtt_topics"]["command_in"],
                mower["protocol"],
                timeout=timeout,
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
            rain_delay = self._coerce_int(
                rain_delay, "rain_delay", minimum=0, maximum=1440
            )
            if mower["protocol"] == 0:
                await self.mqtt.apublish(
                    serial_number,
                    mower["mqtt_topics"]["command_in"],
                    {"rd": rain_delay},
                    mower["protocol"],
                )
            else:
                # Protocol 1 requires rd to be wrapped in cfg
                await self.mqtt.apublish(
                    mower["uuid"],
                    mower["mqtt_topics"]["command_in"],
                    {"cfg": {"rd": rain_delay}},
                    mower["protocol"],
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
        state = self._require_bool(state, "state")
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

    async def set_party_mode(self, serial_number: str, state: bool) -> None:
        """Turn on or off the party mode.

        Args:
            serial_number (str): Serial number of the device
            state (bool): True is enabling party mode, False is disabling party mode.

        Raises:
            NoPartymodeError: Raised if the device does not support party mode.
            OfflineError: Raised if the device is offline.
        """
        state = self._require_bool(state, "state")
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
                        (
                            {"cmd": 0, "sc": {"enabled": 0}}
                            if state
                            else {"cmd": 0, "sc": {"enabled": 1}}
                        ),
                        mower["protocol"],
                    )
            elif not device.capabilities.check(DeviceCapability.PARTY_MODE):
                raise NoPartymodeError("This device does not support Party mode")
        elif not mower["online"]:
            raise OfflineError("The device is currently offline, no action was sent.")

    async def set_pause_mode(self, serial_number: str, state: bool) -> None:
        """Deprecated compatibility wrapper for :meth:`set_party_mode`."""
        import warnings

        warnings.warn(
            "set_pause_mode() is deprecated; use set_party_mode() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        await self.set_party_mode(serial_number, state)

    async def set_offlimits(self, serial_number: str, state: bool) -> None:
        """Turn on or off the off limits module.

        Args:
            serial_number (str): Serial number of the device
            state (bool): True is enabling off limits module, False is disabling off limits module.

        Raises:
            NoOfflimitsError: Raised if the device does not support off limits.
            OfflineError: Raised if the device is offline.
        """
        state = self._require_bool(state, "state")
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
        state = self._require_bool(state, "state")
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
            zone = self._coerce_int(zone, "zone", minimum=0)

            if (
                zone >= len(device.zone["starting_point"])
                or device.zone["starting_point"][zone] == 0
            ):
                raise ZoneNotDefined(
                    f"Cannot request zone {zone} as it is not defined."
                )

            if zone not in device.zone["indicies"]:
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
        enable = self._require_bool(enable, "enable")
        mower = self.get_mower(serial_number)
        current_payload = self._get_current_schedule_payload(mower)
        sc_patch = {"m": 1} if enable else {"m": 0}
        if mower["protocol"] == 1:
            sc_patch = {"enabled": 1} if enable else {"enabled": 0}
        await self._publish_schedule_payload(
            mower,
            self._deep_merge_dict(current_payload, sc_patch),
        )

    async def toggle_auto_schedule(self, serial_number: str, enable: bool) -> None:
        """Turn automatic scheduling on or off.

        This helper is intentionally narrow and experimental. Current live
        findings only confirm that ``auto_schedule`` is surfaced as a top-level
        mower field, so this helper only toggles that observed flag.
        """
        enable = self._require_bool(enable, "enable")
        mower = self.get_mower(serial_number)
        await self._api.check_token()
        response = await APUT(
            f"https://{self._api.cloud.ENDPOINT}/api/v2/product-items/{serial_number}",
            {"auto_schedule": enable},
            HEADERS(self._api.access_token),
            session=await self._api._ensure_session(),
        )

        if isinstance(response, dict):
            mower.update(response)
        mower["auto_schedule"] = enable
        device = self.devices.get(mower["name"])
        if device is not None:
            auto_schedule = device.schedules.get("auto_schedule")
            if isinstance(auto_schedule, dict):
                auto_schedule["enabled"] = enable

        await self._fetch(True)

    async def set_firmware_auto_upgrade(
        self, serial_number: str, enabled: bool
    ) -> None:
        """Turn automatic firmware upgrades on or off."""
        enabled = self._require_bool(enabled, "enabled")
        mower = self.get_mower(serial_number)

        await self._api.check_token()
        response = await APUT(
            f"https://{self._api.cloud.ENDPOINT}/api/v2/product-items/{serial_number}",
            {"firmware_auto_upgrade": enabled},
            HEADERS(self._api.access_token),
            session=await self._api._ensure_session(),
        )

        if isinstance(response, dict):
            mower.update(response)
        mower["firmware_auto_upgrade"] = enabled
        device = self.devices.get(mower["name"])
        if device is not None and isinstance(getattr(device, "firmware", None), dict):
            device.firmware["auto_upgrade"] = enabled

        await self._fetch(True)

    async def get_firmware_upgrade_info(self, serial_number: str) -> dict[str, Any]:
        """Fetch firmware upgrade metadata and availability for a mower."""
        mower = self.get_mower(serial_number)
        device = self.devices.get(mower["name"])

        await self._api.check_token()
        try:
            response = await AGET(
                f"https://{self._api.cloud.ENDPOINT}/api/v2/product-items/{serial_number}/firmware-upgrade",
                HEADERS(self._api.access_token),
                session=await self._api._ensure_session(),
            )
        except NotFoundError:
            response = None

        if response is not None and not isinstance(response, dict):
            raise ValueError("Unexpected firmware-upgrade response payload")

        product = None
        head = None
        ota_supported = self._firmware_ota_supported(mower, device)
        upgrade_failed = False
        if isinstance(response, dict):
            product = self._normalize_firmware_info_entry(response.get("product"))
            head = self._normalize_firmware_info_entry(response.get("head"))
            ota_supported = response.get("has_ota_upgrade", ota_supported)
            upgrade_failed = bool(response.get("upgrade_failed", False))
        current_version = mower.get("firmware_version")
        latest_version = product["version"] if isinstance(product, dict) else None
        update_available = (
            latest_version is not None
            and current_version is not None
            and str(latest_version) != str(current_version)
        )

        normalized = {
            "mandatory": (
                bool(response.get("mandatory", False))
                if isinstance(response, dict)
                else False
            ),
            "current_version": current_version,
            "latest_version": latest_version,
            "update_available": update_available,
            "ota_supported": ota_supported,
            "auto_upgrade": mower.get("firmware_auto_upgrade"),
            "upgrade_failed": upgrade_failed,
            "product": product,
            "head": head,
        }
        self._cache_firmware_upgrade_info(mower, normalized)
        return normalized

    async def start_firmware_upgrade(self, serial_number: str) -> Any:
        """Queue an OTA firmware upgrade for a mower when available."""
        mower = self.get_mower(serial_number)
        device = self.devices.get(mower["name"])
        ota_supported = self._firmware_ota_supported(mower, device)
        if ota_supported is False:
            raise NoFirmwareOtaError(
                "This device does not support OTA firmware upgrades"
            )

        await self._api.check_token()
        _LOGGER.debug("Triggering firmware upgrade for '%s'", mower["name"])
        try:
            response = await APOST(
                f"https://{self._api.cloud.ENDPOINT}/api/v2/product-items/{serial_number}/firmware-upgrade",
                "",
                HEADERS(self._api.access_token),
                session=await self._api._ensure_session(),
            )
        except (NotFoundError, RequestError) as err:
            _LOGGER.debug(
                "Firmware upgrade rejected for '%s': no OTA update available",
                mower["name"],
            )
            raise NoFirmwareAvailableError("No firmware available") from err

        firmware_upgrade = mower.get("firmware_upgrade")
        if isinstance(firmware_upgrade, dict):
            firmware_upgrade["command_queued"] = True
            firmware_upgrade["upgrade_failed"] = False
        if device is not None and isinstance(getattr(device, "firmware", None), dict):
            upgrade = device.firmware.get("upgrade")
            if isinstance(upgrade, dict):
                upgrade["command_queued"] = True
                upgrade["upgrade_failed"] = False

        await self._fetch(True)
        return response

    def _update_cached_lawn(
        self, mower: dict[str, Any], patch: dict[str, int | None]
    ) -> None:
        """Keep cached mower/device lawn values aligned with top-level API writes."""
        if "lawn_size" in patch:
            mower["lawn_size"] = patch["lawn_size"]
        if "lawn_perimeter" in patch:
            mower["lawn_perimeter"] = patch["lawn_perimeter"]

        device = self.devices.get(mower["name"])
        if device is None:
            return

        current_perimeter = mower.get("lawn_perimeter")
        current_size = mower.get("lawn_size")
        if isinstance(getattr(device, "lawn", None), dict):
            device.lawn["perimeter"] = current_perimeter
            device.lawn["size"] = current_size
        else:
            device.lawn = Lawn(current_perimeter, current_size)

    async def set_lawn_size(self, serial_number: str, lawn_size: int) -> None:
        """Set mower lawn size (m²) via top-level product-items REST field."""
        lawn_size = self._coerce_int(lawn_size, "lawn_size", minimum=0)
        mower = self.get_mower(serial_number)

        await self._api.check_token()
        response = await APUT(
            f"https://{self._api.cloud.ENDPOINT}/api/v2/product-items/{serial_number}",
            {"lawn_size": lawn_size},
            HEADERS(self._api.access_token),
            session=await self._api._ensure_session(),
        )

        if isinstance(response, dict):
            mower.update(response)
        self._update_cached_lawn(mower, {"lawn_size": lawn_size})
        await self._fetch(True)

    async def set_lawn_perimeter(self, serial_number: str, lawn_perimeter: int) -> None:
        """Set mower lawn perimeter (m) via top-level product-items REST field."""
        lawn_perimeter = self._coerce_int(lawn_perimeter, "lawn_perimeter", minimum=0)
        mower = self.get_mower(serial_number)

        await self._api.check_token()
        response = await APUT(
            f"https://{self._api.cloud.ENDPOINT}/api/v2/product-items/{serial_number}",
            {"lawn_perimeter": lawn_perimeter},
            HEADERS(self._api.access_token),
            session=await self._api._ensure_session(),
        )

        if isinstance(response, dict):
            mower.update(response)
        self._update_cached_lawn(mower, {"lawn_perimeter": lawn_perimeter})
        await self._fetch(True)

    async def set_lawn(self, serial_number: str, size: int, perimeter: int) -> None:
        """Set both lawn size (m²) and perimeter (m) in a single REST write."""
        lawn_size = self._coerce_int(size, "size", minimum=0)
        lawn_perimeter = self._coerce_int(perimeter, "perimeter", minimum=0)
        mower = self.get_mower(serial_number)
        patch = {
            "lawn_size": lawn_size,
            "lawn_perimeter": lawn_perimeter,
        }

        await self._api.check_token()
        response = await APUT(
            f"https://{self._api.cloud.ENDPOINT}/api/v2/product-items/{serial_number}",
            patch,
            HEADERS(self._api.access_token),
            session=await self._api._ensure_session(),
        )

        if isinstance(response, dict):
            mower.update(response)
        self._update_cached_lawn(mower, patch)
        await self._fetch(True)

    async def set_auto_schedule_boost(self, serial_number: str, boost: int) -> None:
        """Set the observed auto-schedule boost level."""
        boost = self._coerce_int(boost, "boost")
        if boost not in (0, 1, 2):
            raise ValueError("boost must be one of 0, 1, or 2")

        await self._put_auto_schedule_settings_patch(serial_number, {"boost": boost})

    async def set_auto_schedule_grass_type(
        self, serial_number: str, grass_type: str
    ) -> None:
        """Set the observed auto-schedule grass type."""
        if not isinstance(grass_type, str):
            raise ValueError("grass_type must be a string value")
        grass_type = grass_type.strip()
        if grass_type not in {
            "mixed_species",
            "festuca_arundinacea",
            "lolium_perenne",
            "poa_pratensis",
            "festuca_rubra",
            "agrostis_stolonifera",
        }:
            raise ValueError(
                "grass_type must be one of mixed_species, festuca_arundinacea, "
                "lolium_perenne, poa_pratensis, festuca_rubra, or "
                "agrostis_stolonifera"
            )

        await self._put_auto_schedule_settings_patch(
            serial_number, {"grass_type": grass_type}
        )

    async def set_auto_schedule_soil_type(
        self, serial_number: str, soil_type: str
    ) -> None:
        """Set the observed auto-schedule soil type."""
        if not isinstance(soil_type, str):
            raise ValueError("soil_type must be a string value")
        soil_type = soil_type.strip()
        if soil_type not in {"clay", "silt", "sand", "ignore"}:
            raise ValueError("soil_type must be one of clay, silt, sand, or ignore")

        await self._put_auto_schedule_settings_patch(
            serial_number, {"soil_type": soil_type}
        )

    async def set_auto_schedule_irrigation(
        self, serial_number: str, enabled: bool
    ) -> None:
        """Set the observed auto-schedule irrigation flag."""
        enabled = self._require_bool(enabled, "enabled")
        await self._put_auto_schedule_settings_patch(
            serial_number, {"irrigation": enabled}
        )

    async def set_auto_schedule_nutrition(
        self, serial_number: str, n: int, p: int, k: int
    ) -> None:
        """Set the observed auto-schedule nutrition NPK values."""
        nutrition = {
            "n": self._coerce_int(n, "n", minimum=0),
            "p": self._coerce_int(p, "p", minimum=0),
            "k": self._coerce_int(k, "k", minimum=0),
        }
        await self._put_auto_schedule_settings_patch(
            serial_number, {"nutrition": nutrition}
        )

    async def clear_auto_schedule_nutrition(self, serial_number: str) -> None:
        """Clear the observed auto-schedule nutrition settings."""
        await self._put_auto_schedule_settings_patch(serial_number, {"nutrition": None})

    async def set_auto_schedule_exclude_nights(
        self, serial_number: str, enabled: bool
    ) -> None:
        """Set the observed exclusion-scheduler exclude-nights flag."""
        enabled = self._require_bool(enabled, "enabled")
        await self._put_auto_schedule_settings_patch(
            serial_number, {"exclusion_scheduler": {"exclude_nights": enabled}}
        )

    async def set_auto_schedule_exclusion_day(
        self, serial_number: str, day_index: int, exclude_day: bool
    ) -> None:
        """Set whether one exclusion-scheduler weekday is fully excluded."""
        day_index = self._coerce_int(day_index, "day_index", minimum=0, maximum=6)
        exclude_day = self._require_bool(exclude_day, "exclude_day")

        mower = self.get_mower(serial_number)
        current_settings = self._clone_dict(mower.get("auto_schedule_settings"))
        exclusion = current_settings.get("exclusion_scheduler", {})
        days = self._normalize_auto_schedule_exclusion_days_for_write(
            exclusion.get("days") if isinstance(exclusion, dict) else None
        )
        days[day_index]["exclude_day"] = exclude_day

        await self._put_auto_schedule_settings_patch(
            serial_number, {"exclusion_scheduler": {"days": days}}
        )

    async def set_auto_schedule_exclusion_slots(
        self, serial_number: str, day_index: int, slots: list[dict[str, Any]]
    ) -> None:
        """Replace one weekday's exclusion-scheduler slots."""
        day_index = self._coerce_int(day_index, "day_index", minimum=0, maximum=6)
        normalized_slots = self._normalize_auto_schedule_exclusion_slots_for_write(
            slots
        )

        mower = self.get_mower(serial_number)
        current_settings = self._clone_dict(mower.get("auto_schedule_settings"))
        exclusion = current_settings.get("exclusion_scheduler", {})
        days = self._normalize_auto_schedule_exclusion_days_for_write(
            exclusion.get("days") if isinstance(exclusion, dict) else None
        )
        days[day_index]["slots"] = normalized_slots

        await self._put_auto_schedule_settings_patch(
            serial_number, {"exclusion_scheduler": {"days": days}}
        )

    async def set_time_extension(self, serial_number: str, time_extension: int) -> None:
        """Set schedule time extension percentage.

        Args:
            serial_number (str): Serial number of the device
            time_extension (int): Schedule time extension percentage.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        time_extension = self._coerce_int(
            time_extension, "time_extension", minimum=-100, maximum=100
        )
        time_extension = self._require_step(time_extension, "time_extension", 10)
        mower = self.get_mower(serial_number)
        if mower["protocol"] != 0:
            raise ValueError(
                "time_extension is only supported for protocol 0 schedules"
            )
        current_payload = self._get_current_schedule_payload(mower)
        await self._publish_schedule_payload(
            mower,
            self._deep_merge_dict(current_payload, {"p": time_extension}),
        )

    async def set_torque(self, serial_number: str, torque: int) -> None:
        """Set wheel torque percentage.

        Args:
            serial_number (str): Serial number of the device
            torque (int): Wheel torque percentage.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        torque = self._coerce_int(torque, "torque", minimum=-50, maximum=50)
        mower = self.get_mower(serial_number)
        if mower["online"]:
            if mower["protocol"] == 0:
                await self.mqtt.apublish(
                    serial_number,
                    mower["mqtt_topics"]["command_in"],
                    {"tq": torque},
                    mower["protocol"],
                )
            else:
                # Protocol 1 requires tq to be wrapped in cfg
                await self.mqtt.apublish(
                    mower["uuid"],
                    mower["mqtt_topics"]["command_in"],
                    {"cfg": {"tq": torque}},
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

    async def ots(
        self,
        serial_number: str,
        boundary: bool,
        runtime: str,
    ) -> None:
        """Start a One-Time-Schedule task

        Args:
            serial_number (str): Serial number of the device
            boundary (bool): If True the device will start the task cutting the edge.
            runtime (str | int): Minutes to run the task before returning to dock.

        Raises:
            NoOneTimeScheduleError: OTS is not supported by the device.
            OfflineError: Raised when the device is offline.
        """
        boundary = self._require_bool(boundary, "boundary")
        mower = self.get_mower(serial_number)
        if mower["online"]:
            device = DeviceHandler(self._api, mower, self._tz)
            if device.capabilities.check(DeviceCapability.ONE_TIME_SCHEDULE):
                runtime = self._coerce_int(runtime, "runtime", minimum=0)

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

    async def _set_border_cut_settings(
        self,
        serial_number: str,
        *,
        cut_over_border: bool | None = None,
        border_distance: int | None = None,
    ) -> None:
        """Persist protocol 1 border-cut settings without starting a mowing task."""
        if cut_over_border is None and border_distance is None:
            raise ValueError(
                "At least one of cut_over_border or border_distance must be provided"
            )
        if cut_over_border is not None:
            cut_over_border = self._require_bool(cut_over_border, "cut_over_border")
        if border_distance is not None:
            border_distance = self._coerce_int(
                border_distance, "border_distance", minimum=0
            )
            if border_distance not in VISION_BORDER_DISTANCE_MM_VALUES:
                raise ValueError("border_distance must be one of 50, 100, 150, or 200")

        mower = self.get_mower(serial_number)
        if mower["protocol"] != 1:
            raise ValueError(
                "Border-cut settings are only supported for protocol 1 devices"
            )
        if not mower["online"]:
            raise OfflineError("The device is currently offline, no action was sent.")

        device = DeviceHandler(self._api, mower, self._tz)
        if not device.capabilities.check(DeviceCapability.ONE_TIME_SCHEDULE):
            raise NoOneTimeScheduleError(
                "This device does not support border-cut settings"
            )

        cut_payload = self._build_border_cut_settings_payload(
            cut_over_border=cut_over_border,
            border_distance=border_distance,
        )
        await self.mqtt.apublish(
            mower["uuid"],
            mower["mqtt_topics"]["command_in"],
            {"cut": cut_payload},
            mower["protocol"],
        )

        last_status = mower.get("last_status")
        if isinstance(last_status, dict):
            payload = last_status.get("payload")
            if isinstance(payload, dict):
                cfg = payload.setdefault("cfg", {})
                if isinstance(cfg, dict):
                    top_level_cut = cfg.get("cut")
                    if isinstance(top_level_cut, dict):
                        if cut_over_border is not None:
                            top_level_cut["ob"] = int(cut_over_border)
                        if border_distance is not None:
                            top_level_cut["bd"] = border_distance
                    else:
                        cfg["cut"] = self._clone_dict(cut_payload)
                    device_handler = self.devices.get(mower["name"])
                    if device_handler is not None:
                        device_handler.raw_data = json.dumps(payload)

        await self._schedule_api_refresh()

    async def set_border_cut_settings(
        self,
        serial_number: str,
        *,
        cut_over_border: bool,
        border_distance: int,
    ) -> None:
        """Persist both protocol 1 border-cut settings in one command."""
        await self._set_border_cut_settings(
            serial_number,
            cut_over_border=cut_over_border,
            border_distance=border_distance,
        )

    async def set_cut_over_border(
        self, serial_number: str, cut_over_border: bool
    ) -> None:
        """Persist whether border cutting may cross the lawn border."""
        await self._set_border_cut_settings(
            serial_number,
            cut_over_border=cut_over_border,
        )

    async def set_border_distance(
        self, serial_number: str, border_distance: int
    ) -> None:
        """Persist the border-cut distance in millimeters."""
        await self._set_border_cut_settings(
            serial_number,
            border_distance=border_distance,
        )

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
        height = self._coerce_int(height, "height", minimum=0)
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
        state = self._require_bool(state, "state")
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
