"""pyWorxCloud definition."""

# pylint: disable=undefined-loop-variable
# pylint: disable=line-too-long
# pylint: disable=too-many-lines
from __future__ import annotations

from asyncio import sleep
import json
import logging
import sys
import threading
from datetime import datetime, timedelta
from typing import Any

from .api import LandroidCloudAPI
from .clouds import CloudType
from .day_map import DAY_MAP
from .events import EventHandler, LandroidEvent
from .exceptions import (
    AuthorizationError,
    InvalidDataDecodeException,
    MowerNotFoundError,
    NoOneTimeScheduleError,
    NoPartymodeError,
    OfflineError,
    TooManyRequestsError,
    ZoneNoProbability,
    ZoneNotDefined,
)
from .helpers import convert_to_time, get_logger
from .utils import (
    MQTT,
    Battery,
    DeviceCapability,
    DeviceHandler,
    Location,
    Orientation,
    ScheduleType,
    Statistic,
    Weekdays,
)
from .utils.mqtt import Command
from .utils.schedules import TYPE_TO_STRING

if sys.version_info < (3, 9, 0):
    sys.exit("The pyWorxcloud module requires Python 3.9.0 or later")

_LOGGER = logging.getLogger(__name__)

REFRESH_TIME = 15


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
        self._api = LandroidCloudAPI(username, password, cloud)
        self._username = username
        self._cloud = cloud
        self._auth_result = False
        _LOGGER.debug("Getting logger ...")
        self._log = get_logger("pyworxcloud")
        self._raw = None
        self._tz = tz

        self._save_zones = None
        self._verify_ssl = verify_ssl
        _LOGGER.debug("Initializing EventHandler ...")
        self._events = EventHandler()

        self._endpoint = None
        self._user_id = None
        self._mowers = None

        # Dict holding refresh timers
        self._timers = {}

        # Dict of devices, identified by name
        self.devices = {}

        self.mqtt = None

    def __enter__(self) -> Any:
        """Default actions using with statement."""
        self.authenticate()

        self.connect()

        return self

    def __exit__(self, exc_type, exc_value, traceback) -> Any:
        """Called on end of with statement."""
        self.disconnect()

    def authenticate(self) -> bool:
        """Authenticate against the API."""
        self._log.debug("Authenticating %s", self._username)

        try:
            self._api.get_token()
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

    def disconnect(self) -> None:
        """Close API connections."""
        # pylint: disable=bare-except
        logger = self._log.getChild("Disconnect")

        # Cancel force refresh timer on disconnect
        try:
            for _, tmr in self._timers.items():
                tmr.cancel()
        except:
            logger.debug("Could not cancel timers - skipping.")

        # Disconnect MQTT connection
        try:
            if self.mqtt:
                self.mqtt.disconnect()
        except:
            logger.debug("Could not disconnect MQTT - skipping.")

    def connect(
        self,
    ) -> bool:
        """
        Connect to the cloud service endpoint

        Returns:
            bool: True if connection was successful, otherwise False.
        """
        self._log.debug("Fetching basic API data")
        self._fetch()
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
        )

        self.mqtt.connect()
        while self.mqtt.connected is False:
            pass

        for mower in self._mowers:
            self.mqtt.subscribe(mower["mqtt_topics"]["command_out"])
            self._schedule_forced_refresh(mower["serial_number"])

        self._log.debug("MQTT connect done")

        # Convert time strings to objects.
        for name, device in self.devices.items():
            convert_to_time(
                name, device, device.time_zone, callback=self.update_attribute
            )
        self._log.debug("Connection tasks all done")

        return True

    @property
    def auth_result(self) -> bool:
        """Return current authentication result."""
        return self._auth_result

    def _schedule_forced_refresh(self, serial_number: str) -> None:
        """Schedule a forced refresh."""
        logger = self._log.getChild("Refresh_Scheduler")
        name = None
        for mower in self._mowers:
            if mower["serial_number"] == serial_number:
                name = mower["name"]
                break

        if isinstance(name, type(None)):
            logger.warning(
                "Didn't find any mowers with serial number '%s'", serial_number
            )
            return None

        next_refresh = datetime.now() + timedelta(minutes=REFRESH_TIME)
        logger.debug(
            "Scheduling a forced refresh for '%s' at %s",
            name,
            next_refresh,
        )

        force_refresh = threading.Timer(
            REFRESH_TIME * 60, self._force_refresh, args=[serial_number, name]
        )
        force_refresh.start()
        self._timers.update({serial_number: force_refresh})

    def _force_refresh(
        self, *args, **kwargs  # pylint: disable=unused-argument
    ) -> None:
        """Handle for refreshing device."""
        logger = self._log.getChild("Forced_Refresh")
        logger.debug("Forcing refresh for '%s'", args[1])
        self.update(args[0])

        self._schedule_forced_refresh(args[0])

    def _on_update(self, payload):  # , topic, payload, dup, qos, retain, **kwargs):
        """Triggered when a MQTT message was received."""
        logger = self._log.getChild("MQTT_data_in")
        try:
            data = json.loads(payload)
            logger.debug("MQTT data received")

            # "Malformed" message, we are missing a serial number and
            # MAC address to identify the mower.
            if (
                not "sn" in data["cfg"] and not "uuid" in data["dat"]
            ) and not "mac" in data["dat"]:
                logger.debug("Malformed message received")
                return

            found_match = False

            for mower in self._mowers:
                if "sn" in data["cfg"]:
                    if mower["serial_number"] == data["cfg"]["sn"]:
                        found_match = True
                        break
                elif "uuid" in data["dat"]:
                    if mower["uuid"] == data["dat"]["uuid"]:
                        found_match = True
                        break
                elif "mac" in data["dat"]:
                    if mower["mac_address"] == data["dat"]["mac"]:
                        found_match = True
                        break

            if not found_match:
                logger.debug("Could not match incoming data with a known mower!")
                return
            else:
                logger.debug("Matched to '%s'", mower["name"])

            device: DeviceHandler = self.devices[mower["name"]]
            (self._timers[mower["serial_number"]]).cancel()
            self._schedule_forced_refresh(mower["serial_number"])

            while not device.is_decoded:
                pass  # Wait for last dataset to be handled

            if device.raw_data == data:
                self._log.debug("Data was already present and not changed.")
                return  # Dataset was not changed, no update needed

            device.raw_data = payload
            self._decode_data(device)

            self._events.call(
                LandroidEvent.DATA_RECEIVED, name=mower["name"], device=device
            )
        except json.decoder.JSONDecodeError:
            logger.debug("Malformed MQTT message received")

    def _decode_data(self, device: DeviceHandler) -> None:
        """Decode incoming JSON data."""
        invalid_data = False

        device.is_decoded = False

        logger = self._log.getChild("decode_data")
        logger.debug("Data decoding for %s started", device.name)

        if device.json_data:
            logger.debug("Found JSON decoded data: %s", device.json_data)
            data = device.json_data
        elif device.raw_data:
            logger.debug("Found raw data: %s", device.raw_data)
            data = device.raw_data
        else:
            device.is_decoded = True
            logger.debug("No valid data was found, skipping update for %s", device.name)
            return

        mower = device.mower
        if "dat" in data:
            mower["last_status"]["payload"]["dat"] = data["dat"]
            if "uuid" in data["dat"]:
                device.uuid = data["dat"]["uuid"]

            if isinstance(device.mac_address, type(None)):
                device.mac_address = (
                    data["dat"]["mac"] if "mac" in data["dat"] else "__UUID__"
                )

            try:
                # Get wifi signal strength
                if "rsi" in data["dat"]:
                    device.rssi = data["dat"]["rsi"]

                # Get status code
                if "ls" in data["dat"]:
                    device.status.update(data["dat"]["ls"])

                # Get error code
                if "le" in data["dat"]:
                    device.error.update(data["dat"]["le"])

                # Get zone index
                device.zone.index = data["dat"]["lz"] if "lz" in data["dat"] else 0

                # Get device lock state
                device.locked = bool(data["dat"]["lk"]) if "lk" in data["dat"] else None
                mower["locked"] = device.locked

                # Get battery info if available
                if "bt" in data["dat"]:
                    if len(device.battery) == 0:
                        device.battery = Battery(data["dat"]["bt"])
                    else:
                        device.battery.set_data(data["dat"]["bt"])
                # Get device statistics if available
                if "st" in data["dat"]:
                    device.statistics = Statistic(data["dat"]["st"])

                    if len(device.blades) != 0:
                        device.blades.set_data(data["dat"]["st"])

                # Get orientation if available.
                if "dmp" in data["dat"]:
                    device.orientation = Orientation(data["dat"]["dmp"])

                # Check for extra module availability
                if "modules" in data["dat"]:
                    if "4G" in data["dat"]["modules"]:
                        device.gps = Location(
                            data["dat"]["modules"]["4G"]["gps"]["coo"][0],
                            data["dat"]["modules"]["4G"]["gps"]["coo"][1],
                        )

                # Get remaining rain delay if available
                if "rain" in data["dat"]:
                    device.rainsensor.triggered = bool(
                        str(data["dat"]["rain"]["s"]) == "1"
                    )
                    device.rainsensor.remaining = int(data["dat"]["rain"]["cnt"])
            except TypeError:  # pylint: disable=bare-except
                invalid_data = True

        if "cfg" in data:
            mower["last_status"]["payload"]["cfg"] = data["cfg"]
            # try:
            if "dt" in data["cfg"]:
                dt_split = data["cfg"]["dt"].split("/")
                date = (
                    f"{dt_split[2]}-{dt_split[1]}-{dt_split[0]}"
                    + " "
                    + data["cfg"]["tm"]
                )
            elif "tm" in data["dat"]:
                date = datetime.fromisoformat(data["dat"]["tm"])
            else:
                date = datetime.now()

            device.updated = date
            device.rainsensor.delay = int(data["cfg"]["rd"])

            # Fetch wheel torque
            if "tq" in data["cfg"]:
                device.capabilities.add(DeviceCapability.TORQUE)
                device.torque = data["cfg"]["tq"]

            # Fetch zone information
            if "mz" in data["cfg"] and "mzv" in data["cfg"]:
                device.zone.starting_point = data["cfg"]["mz"]
                device.zone.indicies = data["cfg"]["mzv"]

                # Map current zone to zone index
                device.zone.current = device.zone.indicies[device.zone.index]

            # Fetch main schedule
            if "sc" in data["cfg"]:
                if "ots" in data["cfg"]["sc"]:
                    device.capabilities.add(DeviceCapability.ONE_TIME_SCHEDULE)
                    device.capabilities.add(DeviceCapability.EDGE_CUT)
                if "distm" in data["cfg"]["sc"] or "enabled" in data["cfg"]["sc"]:
                    device.capabilities.add(DeviceCapability.PARTY_MODE)

                device.partymode_enabled = (
                    bool(str(data["cfg"]["sc"]["m"]) == "2")
                    if device.protocol == 0
                    else bool(str(data["cfg"]["sc"]["enabled"]) == "0")
                )
                device.schedules["active"] = (
                    bool(str(data["cfg"]["sc"]["m"]) in ["1", "2"])
                    if device.protocol == 0
                    else bool(str(data["cfg"]["sc"]["enabled"]) == "0")
                )

                device.schedules["time_extension"] = (
                    data["cfg"]["sc"]["p"] if device.protocol == 0 else "0"
                )

                sch_type = ScheduleType.PRIMARY
                device.schedules.update({TYPE_TO_STRING[sch_type]: Weekdays()})

                for day in range(
                    0,
                    (
                        len(data["cfg"]["sc"]["d"])
                        if device.protocol == 0
                        else len(data["cfg"]["sc"]["slots"])
                    ),
                ):
                    dayOfWeek = (  # pylint: disable=invalid-name
                        day
                        if device.protocol == 0
                        else data["cfg"]["sc"]["slots"][day]["d"]
                    )
                    device.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[dayOfWeek]][
                        "start"
                    ] = (
                        data["cfg"]["sc"]["d"][day][0]
                        if device.protocol == 0
                        else (
                            datetime.strptime("00:00", "%H:%M")
                            + timedelta(minutes=data["cfg"]["sc"]["slots"][day]["s"])
                        ).strftime("%H:%M")
                    )
                    device.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[dayOfWeek]][
                        "duration"
                    ] = (
                        data["cfg"]["sc"]["d"][day][1]
                        if device.protocol == 0
                        else data["cfg"]["sc"]["slots"][day]["t"]
                    )
                    device.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[dayOfWeek]][
                        "boundary"
                    ] = (
                        bool(data["cfg"]["sc"]["d"][day][2])
                        if device.protocol == 0
                        else (
                            bool(data["cfg"]["sc"]["slots"][day]["cfg"]["cut"]["b"])
                            if "b" in data["cfg"]["sc"]["slots"][day]["cfg"]["cut"]
                            else None
                        )
                    )

                    time_start = datetime.strptime(
                        device.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[dayOfWeek]][
                            "start"
                        ],
                        "%H:%M",
                    )

                    if isinstance(
                        device.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[dayOfWeek]][
                            "duration"
                        ],
                        type(None),
                    ):
                        device.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[dayOfWeek]][
                            "duration"
                        ] = "0"

                    duration = int(
                        device.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[dayOfWeek]][
                            "duration"
                        ]
                    )

                    duration = duration * (
                        1 + (int(device.schedules["time_extension"]) / 100)
                    )
                    end_time = time_start + timedelta(minutes=duration)

                    device.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[dayOfWeek]][
                        "end"
                    ] = end_time.time().strftime("%H:%M")

                # Fetch secondary schedule
                if "dd" in data["cfg"]["sc"]:
                    sch_type = ScheduleType.SECONDARY
                    device.schedules.update({TYPE_TO_STRING[sch_type]: Weekdays()})

                    for day in range(0, len(data["cfg"]["sc"]["dd"])):
                        device.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                            "start"
                        ] = data["cfg"]["sc"]["dd"][day][0]
                        device.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                            "duration"
                        ] = data["cfg"]["sc"]["dd"][day][1]
                        device.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                            "boundary"
                        ] = bool(data["cfg"]["sc"]["dd"][day][2])

                        time_start = datetime.strptime(
                            data["cfg"]["sc"]["dd"][day][0],
                            "%H:%M",
                        )

                        if isinstance(
                            device.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                                "duration"
                            ],
                            type(None),
                        ):
                            device.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                                "duration"
                            ] = "0"

                        duration = int(
                            device.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                                "duration"
                            ]
                        )

                        duration = duration * (
                            1 + (int(device.schedules["time_extension"]) / 100)
                        )
                        end_time = time_start + timedelta(minutes=duration)

                        device.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                            "end"
                        ] = end_time.time().strftime("%H:%M")

            device.schedules.update_progress_and_next(
                tz=(
                    self._tz
                    if not isinstance(self._tz, type(None))
                    else device.time_zone
                )
            )
            # except TypeError:
            #     invalid_data = True
            # except KeyError:
            #     invalid_data = True

        convert_to_time(
            device.name, device, device.time_zone, callback=self.update_attribute
        )

        mower["last_status"]["timestamp"] = device.updated

        device.is_decoded = True
        logger.debug("Data for %s was decoded", device.name)

        if invalid_data:
            raise InvalidDataDecodeException()

    def _fetch(self) -> None:
        """Fetch base API information."""
        self._mowers = self._api.get_mowers()

        for mower in self._mowers:
            device = DeviceHandler(self._api, mower)
            _LOGGER.debug("Mower '%s' data: %s", mower["name"], mower)
            self.devices.update({mower["name"]: device})

            try:
                if not isinstance(mower["last_status"], type(None)):
                    device.raw_data = mower["last_status"]["payload"]
            except TypeError:
                pass

            self._decode_data(device)

            if isinstance(mower["mac_address"], type(None)):
                mower["mac_address"] = (
                    device.raw_data["dat"]["mac"]
                    if "mac" in device.raw_data["dat"]
                    else "__UUID__"
                )

    def get_mower(self, serial_number: str) -> dict:
        """Get a specific mower object.

        Args:
            serial_number (str): Serial number of the device
        """
        for mower in self._mowers:
            if mower["serial_number"] == serial_number:
                return mower

        raise MowerNotFoundError(
            f"Mower with serialnumber {serial_number} was not found."
        )

    def update(self, serial_number: str) -> None:
        """Request a state refresh."""
        mower = self.get_mower(serial_number)
        _LOGGER.debug("Trying to refresh '%s'", serial_number)

        self.mqtt.ping(
            serial_number if mower["protocol"] == 0 else mower["uuid"],
            mower["mqtt_topics"]["command_in"],
            mower["protocol"],
        )

    def start(self, serial_number: str) -> None:
        """Start mowing task

        Args:
            serial_number (str): Serial number of the device

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            _LOGGER.debug("Sending start command to '%s'", serial_number)
            self.mqtt.command(
                serial_number if mower["protocol"] == 0 else mower["uuid"],
                mower["mqtt_topics"]["command_in"],
                Command.START,
                mower["protocol"],
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def home(self, serial_number: str) -> None:
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
            self.mqtt.command(
                serial_number if mower["protocol"] == 0 else mower["uuid"],
                mower["mqtt_topics"]["command_in"],
                Command.HOME,
                mower["protocol"],
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def safehome(self, serial_number: str) -> None:
        """Stop and go home with the blades off

        Args:
            serial_number (str): Serial number of the device

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            self.mqtt.command(
                serial_number if mower["protocol"] == 0 else mower["uuid"],
                mower["mqtt_topics"]["command_in"],
                Command.SAFEHOME,
                mower["protocol"],
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def pause(self, serial_number: str) -> None:
        """Pause the mowing task

        Args:
            serial_number (str): Serial number of the device

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            self.mqtt.command(
                serial_number if mower["protocol"] == 0 else mower["uuid"],
                mower["mqtt_topics"]["command_in"],
                Command.PAUSE,
                mower["protocol"],
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def raindelay(self, serial_number: str, rain_delay: str) -> None:
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
            self.mqtt.publish(
                serial_number if mower["protocol"] == 0 else mower["uuid"],
                mower["mqtt_topics"]["command_in"],
                {"rd": rain_delay},
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def set_lock(self, serial_number: str, state: bool) -> None:
        """Set the device locked state.

        Args:
            serial_number (str): Serial number of the device
            state (bool): True will lock the device, False will unlock the device.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            self.mqtt.command(
                serial_number if mower["protocol"] == 0 else mower["uuid"],
                mower["mqtt_topics"]["command_in"],
                Command.LOCK if state else Command.UNLOCK,
                mower["protocol"],
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def set_partymode(self, serial_number: str, state: bool) -> None:
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
            device = DeviceHandler(self._api, mower)
            if device.capabilities.check(DeviceCapability.PARTY_MODE):
                if mower["protocol"] == 0:
                    self.mqtt.publish(
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
                    self.mqtt.publish(
                        serial_number if mower["protocol"] == 0 else mower["uuid"],
                        mower["mqtt_topics"]["command_in"],
                        {"sc": {"enabled": 0}} if state else {"sc": {"enabled": 1}},
                        mower["protocol"],
                    )
            elif not device.capabilities.check(DeviceCapability.PARTY_MODE):
                raise NoPartymodeError("This device does not support Partymode")
        elif not mower["online"]:
            raise OfflineError("The device is currently offline, no action was sent.")

    def setzone(self, serial_number: str, zone: str | int) -> None:
        """Set zone to be mowed when next mowing task is started.

        Args:
            serial_number (str): Serial number of the device
            zone (str | int): Zone to mow, valid possibilities are a number from 1 to 4.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            device = DeviceHandler(self._api, mower)
            if not isinstance(zone, int):
                zone = int(zone)

            if (
                zone >= len(device.zone["starting_point"])
                or device.zone["starting_point"][zone] == 0
            ):
                raise ZoneNotDefined("Cannot request zone {} as it is not defined.".format(zone))

            if not zone in device.zone["indicies"]:
                raise ZoneNoProbability(
                    "Cannot request zone {} as it has no probability set.".format(zone)
                )

            current_zones = device.zone["indicies"]
            requested_zone_index = current_zones.index(zone)
            next_zone_index = device.zone["index"]

            no_indices = len(current_zones)
            offset = (requested_zone_index - next_zone_index) % no_indices
            new_zones = []
            for i in range(0, no_indices):
                new_zones.append(current_zones[(offset + i) % no_indices])

            device = DeviceHandler(self._api, mower)
            self.mqtt.publish(
                serial_number if mower["protocol"] == 0 else mower["uuid"],
                mower["mqtt_topics"]["command_in"],
                {"mzv": new_zones},
                mower["protocol"],
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def zonetraining(self, serial_number: str) -> None:
        """Start the zone training task.

        Args:
            serial_number (str): Serial number of the device

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            _LOGGER.debug("Sending ZONETRAINING command to %s", mower["name"])
            self.mqtt.command(
                serial_number if mower["protocol"] == 0 else mower["uuid"],
                mower["mqtt_topics"]["command_in"],
                Command.ZONETRAINING,
                mower["protocol"],
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def restart(self, serial_number: str):
        """Reboot the device baseboard.

        Args:
            serial_number (str): Serial number of the device

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            _LOGGER.debug("Sending RESTART command to %s", mower["name"])
            self.mqtt.command(
                serial_number if mower["protocol"] == 0 else mower["uuid"],
                mower["mqtt_topics"]["command_in"],
                Command.RESTART,
                mower["protocol"],
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def toggle_schedule(self, serial_number: str, enable: bool) -> None:
        """Turn on or off the schedule.

        Args:
            serial_number (str): Serial number of the device
            enable (bool): True is enabling the schedule, Fasle is disabling the schedule.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            self.mqtt.publish(
                serial_number if mower["protocol"] == 0 else mower["uuid"],
                mower["mqtt_topics"]["command_in"],
                {"sc": {"m": 1}} if enable else {"sc": {"m": 0}},
                mower["protocol"],
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def ots(self, serial_number: str, boundary: bool, runtime: str) -> None:
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
            device = DeviceHandler(self._api, mower)
            if device.capabilities.check(DeviceCapability.ONE_TIME_SCHEDULE):
                if not isinstance(runtime, int):
                    runtime = int(runtime)

                device = DeviceHandler(self._api, mower)
                self.mqtt.publish(
                    serial_number if mower["protocol"] == 0 else mower["uuid"],
                    mower["mqtt_topics"]["command_in"],
                    {"sc": {"ots": {"bc": int(boundary), "wtm": runtime}}},
                    mower["protocol"],
                )
            elif not device.capabilities.check(DeviceCapability.ONE_TIME_SCHEDULE):
                raise NoOneTimeScheduleError(
                    "This device does not support Edgecut-on-demand"
                )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def send(self, serial_number: str, data: str) -> None:
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
            self.mqtt.publish(
                serial_number if mower["protocol"] == 0 else mower["uuid"],
                mower["mqtt_topics"]["command_in"],
                json.loads(data),
                mower["protocol"],
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")
