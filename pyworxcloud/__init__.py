"""pyWorxCloud definition."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta
from typing import Any

from .api import LandroidCloudAPI
from .clouds import CloudType
from .day_map import DAY_MAP
from .events import EventHandler, LandroidEvent
from .exceptions import (
    AuthorizationError,
    MowerNotFoundError,
    NoOneTimeScheduleError,
    NoPartymodeError,
    OfflineError,
    RequestException,
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
        cloud: CloudType.WORX
        | CloudType.KRESS
        | CloudType.LANDXCAPE
        | str = CloudType.WORX,
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

        self._api.get_token()
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
        self.mqtt.disconnect()

    def connect(
        self,
    ) -> bool:
        """Connect to the cloud service endpoint

        Args:
            index (int | None, optional): Device number to connect to. Defaults to None.
            verify_ssl (bool, optional): Should we verify SSL certificate. Defaults to True.

        Returns:
            bool: True if connection was successful, otherwise False.
        """
        self._log.debug("Fetching basic API data")
        self._fetch()
        self._log.debug("Done fetching basic API data")

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

        self._log.debug("MQTT connect done")

        # Convert time strings to objects.
        self._log.debug("Converting date and time string")
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

    def _on_update(self, payload):  # , topic, payload, dup, qos, retain, **kwargs):
        """Triggered when a MQTT message was received."""
        data = json.loads(payload)
        logger = self._log.getChild("MQTT_data_in")
        logger.debug("MQTT data received")
        # logger.debug("MQTT data received '%s' on topic '%s'", payload, topic)

        for mower in self._mowers:
            if mower["serial_number"] == data["cfg"]["sn"]:
                break

        device: DeviceHandler = self.devices[mower["name"]]

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

    def _decode_data(self, device: DeviceHandler) -> None:
        """Decode incoming JSON data."""
        device.is_decoded = False

        logger = self._log.getChild("decode_data")
        logger.debug("Data decoding for %s started", device.name)

        if device.json_data:
            logger.debug("Found JSON decoded data: %s", device.json_data)
            data = device.json_data
        elif device.raw_data:
            logger.debug("Found raw data: %s", device.raw_data)
            data = json.loads(device.raw_data)
        else:
            device.is_decoded = True
            logger.debug("No valid data was found, skipping update for %s", device.name)
            return

        # device.firmware["version"] = "{:.2f}".format(device.firmware["version"])
        if "dat" in data:
            device.rssi = data["dat"]["rsi"]
            logger.debug("Status code: %s", data["dat"]["ls"])
            device.status.update(data["dat"]["ls"])
            device.error.update(data["dat"]["le"])

            device.zone.index = data["dat"]["lz"]

            device.locked = bool(data["dat"]["lk"])

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
                device.rainsensor.triggered = bool(str(data["dat"]["rain"]["s"]) == "1")
                device.rainsensor.remaining = int(data["dat"]["rain"]["cnt"])

        if "cfg" in data:
            device.updated = data["cfg"]["dt"] + " " + data["cfg"]["tm"]
            device.rainsensor.delay = int(data["cfg"]["rd"])

            # Fetch wheel torque
            if "tq" in data["cfg"]:
                device.capabilities.add(DeviceCapability.TORQUE)
                device.torque = data["cfg"]["tq"]

            # Fetch zone information
            if "mz" in data["cfg"]:
                device.zone.starting_point = data["cfg"]["mz"]
                device.zone.indicies = data["cfg"]["mzv"]

                # Map current zone to zone index
                device.zone.current = device.zone.indicies[device.zone.index]
                # device.zone.current = 1

            # Fetch main schedule
            if "sc" in data["cfg"]:
                if "ots" in data["cfg"]["sc"]:
                    device.capabilities.add(DeviceCapability.ONE_TIME_SCHEDULE)
                    device.capabilities.add(DeviceCapability.EDGE_CUT)
                if "distm" in data["cfg"]["sc"]:
                    device.capabilities.add(DeviceCapability.PARTY_MODE)

                device.partymode_enabled = bool(str(data["cfg"]["sc"]["m"]) == "2")

                device.schedules["active"] = bool(
                    str(data["cfg"]["sc"]["m"]) in ["1", "2"]
                )
                device.schedules["time_extension"] = data["cfg"]["sc"]["p"]

                sch_type = ScheduleType.PRIMARY
                device.schedules.update({TYPE_TO_STRING[sch_type]: Weekdays()})

                for day in range(0, len(data["cfg"]["sc"]["d"])):
                    device.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                        "start"
                    ] = data["cfg"]["sc"]["d"][day][0]
                    device.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                        "duration"
                    ] = data["cfg"]["sc"]["d"][day][1]
                    device.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                        "boundary"
                    ] = bool(data["cfg"]["sc"]["d"][day][2])

                    time_start = datetime.strptime(
                        device.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                            "start"
                        ],
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

            # Fetch secondary schedule
            if "dd" in data["cfg"]["sc"]:
                sch_type = ScheduleType.SECONDARY
                device.schedules.update({TYPE_TO_STRING[sch_type]: Weekdays()})

                for day in range(0, len(data["cfg"]["sc"]["d"])):
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
                tz=self._tz
                if not isinstance(self._tz, type(None))
                else device.time_zone
            )

        convert_to_time(
            device.name, device, device.time_zone, callback=self.update_attribute
        )

        device.is_decoded = True
        logger.debug("Data for %s was decoded", device.name)

    def _fetch(self) -> None:
        """Fetch base API information."""
        self._mowers = self._api.get_mowers()

        for mower in self._mowers:
            device = DeviceHandler(self._api, mower)
            _LOGGER.debug("Mower '%s' data: %s", mower["name"], mower)
            self.devices.update({mower["name"]: device})

            self._decode_data(device)

    def get_mower(self, serial_number: str) -> dict:
        """Get a specific mower."""
        for mower in self._mowers:
            if mower["serial_number"] == serial_number:
                return mower

        raise MowerNotFoundError(
            f"Mower with serialnumber {serial_number} was not found."
        )

    def update(self, serial_number: str) -> None:
        """Request a state refresh."""
        mower = self.get_mower(serial_number)
        _LOGGER.debug("Trying to refreshing '%s'", serial_number)
        self.mqtt.ping(serial_number, mower["mqtt_topics"]["command_in"])

    def start(self, serial_number: str) -> None:
        """Start mowing task

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            _LOGGER.debug("Sending start command to '%s'", serial_number)
            self.mqtt.command(
                serial_number, mower["mqtt_topics"]["command_in"], Command.START
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def home(self, serial_number: str) -> None:
        """Stop the current task and go home.
        If the knifes was turned on when this is called,
        it will return home with knifes still turned on.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)

        if mower["online"]:
            self.mqtt.command(
                serial_number, mower["mqtt_topics"]["command_in"], Command.HOME
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def safehome(self, serial_number: str) -> None:
        """Stop and go home with the blades off

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            self.mqtt.command(
                serial_number, mower["mqtt_topics"]["command_in"], Command.SAFEHOME
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def pause(self, serial_number: str) -> None:
        """Pause the mowing task

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            self.mqtt.command(
                serial_number, mower["mqtt_topics"]["command_in"], Command.PAUSE
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def refresh(self, serial_number: str) -> None:
        """Force a data refresh from API endpoint.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            self.mqtt.command(
                serial_number, mower["mqtt_topics"]["command_in"], Command.FORCE_REFRESH
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def raindelay(self, serial_number: str, rain_delay: str) -> None:
        """Set new rain delay.

        Args:
            rain_delay (str | int): Rain delay in minutes.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            if not isinstance(rain_delay, int):
                rain_delay = int(rain_delay)
            self.mqtt.publish(
                serial_number,
                mower["mqtt_topics"]["command_in"],
                {"rd": rain_delay},
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def set_lock(self, serial_number: str, state: bool) -> None:
        """Set the device locked state.

        Args:
            enabled (bool): True will lock the device, False will unlock the device.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            self.mqtt.command(
                serial_number,
                mower["mqtt_topics"]["command_in"],
                Command.LOCK if state else Command.UNLOCK,
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def set_partymode(self, serial_number: str, state: bool) -> None:
        """Turn on or off the partymode.

        Args:
            enable (bool): True is enabling partymode, Fasle is disabling partymode.

        Raises:
            NoPartymodeError: Raised if the device does not support partymode.
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            device = DeviceHandler(self._api, mower)
            if device.capabilities.check(DeviceCapability.PARTY_MODE):
                self.mqtt.publish(
                    serial_number,
                    mower["mqtt_topics"]["command_in"],
                    {"sc": {"m": 2, "distm": 0}}
                    if state
                    else {"sc": {"m": 1, "distm": 0}},
                )
            elif not device.capabilities.check(DeviceCapability.PARTY_MODE):
                raise NoPartymodeError("This device does not support Partymode")
        elif not mower["online"]:
            raise OfflineError("The device is currently offline, no action was sent.")

    def setzone(self, serial_number: str, zone: str) -> None:
        """Set zone to be mowed when next mowing task is started.

        Args:
            zone (str | int): Zone to mow, valid possibilities are a number from 1 to 4.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            device = DeviceHandler(self._api, mower)
            if not isinstance(zone, int):
                zone = int(zone)

            if device.zone["starting_point"][zone] == 0:
                raise RequestException("Cannot request this zone as it is not defined.")

            current = device.zone["indicies"]
            new_zones = current

            while not new_zones[device.zone["index"]] == zone:
                tmp = []
                for i in range(1, 10):
                    tmp.append(new_zones[i])
                tmp.append(new_zones[0])
                new_zones = tmp

            self.mqtt.publish(
                serial_number,
                mower["mqtt_topics"]["command_in"],
                {"mzv": new_zones},
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def zonetraining(self, serial_number: str) -> None:
        """Start the zone training task.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            _LOGGER.debug("Sending ZONETRAINING command to %s", mower["name"])
            self.mqtt.command(
                serial_number, mower["mqtt_topics"]["command_in"], Command.ZONETRAINING
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def restart(self, serial_number: str):
        """Reboot the device baseboard.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            _LOGGER.debug("Sending RESTART command to %s", mower["name"])
            self.mqtt.command(
                serial_number, mower["mqtt_topics"]["command_in"], Command.RESTART
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def toggle_schedule(self, serial_number: str, enable: bool) -> None:
        """Turn on or off the schedule.

        Args:
            enable (bool): True is enabling the schedule, Fasle is disabling the schedule.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            self.mqtt.publish(
                serial_number,
                mower["mqtt_topics"]["command_in"],
                {"sc": {"m": 1}} if enable else {"sc": {"m": 0}},
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def ots(self, serial_number: str, boundary: bool, runtime: str) -> None:
        """Start a One-Time-Schedule task

        Args:
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

                self.mqtt.publish(
                    serial_number,
                    mower["mqtt_topics"]["command_in"],
                    {"sc": {"ots": {"bc": int(boundary), "wtm": runtime}}},
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
            data (str): Data to be sent, formatted as a valid JSON object.

        Raises:
            OfflineError: Raised if the device isn't online.
        """
        mower = self.get_mower(serial_number)
        if mower["online"]:
            _LOGGER.debug("Sending %s to %s", data, mower["name"])
            self.mqtt.publish(
                serial_number, mower["mqtt_topics"]["command_in"], json.loads(data)
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")
