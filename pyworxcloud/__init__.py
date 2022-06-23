"""pyWorxCloud definition."""
from __future__ import annotations

import base64
import contextlib
import json
import sys
import tempfile
import time
from datetime import datetime, timedelta
from typing import Any

import OpenSSL.crypto
import paho.mqtt.client as mqtt
from paho.mqtt.client import error_string, connack_string

from .clouds import CloudType
from .const import UNWANTED_ATTRIBS
from .day_map import DAY_MAP
from .exceptions import (
    AuthorizationError,
    MQTTException,
    NoOneTimeScheduleError,
    NoPartymodeError,
    OfflineError,
)
from .api import LandroidCloudAPI

from .helpers import convert_to_time, get_logger
from .utils import (
    Blades,
    Battery,
    Capability,
    Command,
    DeviceCapability,
    Location,
    MQTT,
    MQTTData,
    Orientation,
    Rainsensor,
    Schedule,
    ScheduleType,
    States,
    StateType,
    Statistic,
    Zone,
)
from .utils.schedules import TYPE_TO_STRING

if sys.version_info < (3, 10, 0):
    sys.exit("The pyWorxcloud module requires Python 3.10.0 or later")


class WorxCloud(dict):
    """
    Worx by Landroid Cloud connector.

    Used for handling API connection to Worx, Kress and Landxcape devices which are cloud connected.

    This uses a reverse engineered API protocol, so no guarantee that this will keep working.
    There are no public available API documentation available.
    """

    def __init__(
        self,
        username: str,
        password: str,
        cloud: CloudType.WORX
        | CloudType.KRESS
        | CloudType.LANDXCAPE
        | CloudType.FERREX
        | str = CloudType.WORX,
        index: int = 0,
        verify_ssl: bool = True,
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
            cloud (CloudType.WORX | CloudType.KRESS | CloudType.LANDXCAPE | CloudType.FERREX | str, optional): The CloudType matching your device. Defaults to CloudType.WORX.
            index (int, optional): Device number if more than one is connected to your account (starting from 0 representing the first added device). Defaults to 0.
            verify_ssl (bool, optional): Should this module verify the API endpoint SSL certificate? Defaults to True.

        Raise:
            TypeError: Error raised if invalid CloudType was specified.
        """
        self._worx_mqtt_client_id = None

        if not isinstance(
            cloud,
            (
                type(CloudType.WORX),
                type(CloudType.KRESS),
                type(CloudType.LANDXCAPE),
                type(CloudType.FERREX),
            ),
        ):
            try:
                cloud = getattr(CloudType, cloud.upper())
            except AttributeError:
                raise TypeError(
                    "Wrong type specified, valid types are: worx, landxcape, kress, ferrex"
                )

        self._api = LandroidCloudAPI(username, password, cloud)

        self._username = username
        self._cloud = cloud
        self._auth_result = False
        self._callback = None  # Callback used when data arrives from cloud
        self._dev_id = index
        self._log = get_logger("pyworxcloud")
        self._raw = None
        self._mqtt_data = None
        self._save_zones = None
        self._verify_ssl = verify_ssl

        # Set default attribute values
        ###############################
        self.accessories = None
        self.battery = Battery()
        self.blades = Blades()
        self.error = States(StateType.ERROR)
        self.gps = Location()
        self.locked = False
        self.mqtt = MQTT()
        self.mqttdata = MQTTData()
        self.online = False
        self.orientation = Orientation([0, 0, 0])
        self.capabilities = Capability()
        self.partymode_enabled = False
        self.product = []
        self.rainsensor = Rainsensor()
        self.rssi = None
        self.schedules: dict[str, Any] = {"time_extension": 0, "active": True}
        self.serial_number = None
        self.status = States()
        self.torque = None
        self.updated = "never"
        self.work_time = 0
        self.zone = Zone()

    def __enter__(self):
        """Default actions using with statement."""
        if isinstance(self._dev_id, type(None)):
            self._dev_id = 0

        self.authenticate()

        self.connect(self._dev_id, self._verify_ssl)
        self.update()

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Called on end of with statement."""
        self.disconnect()

    def authenticate(self) -> bool:
        """Authenticate against the API."""
        self._log.debug("Authenticating %s", self._username)

        auth = self._authenticate()
        if auth is False:
            self._auth_result = False
            self._log.debug("Authentication for %s failed!", self._username)
            raise AuthorizationError("Unauthorized")

        self._auth_result = True
        self._log.debug("Authentication for %s successful", self._username)

        return True

    def update_attribute(self, attr: str | None, key: str, value: Any) -> None:
        """Used as callback to update value."""
        chattr = self
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

    def set_callback(self, callback) -> None:
        """Set callback which is called when data is received.

        Args:
            callback (function): Function to be called.
        """
        self._callback = callback

    def disconnect(self) -> None:
        """Close API connections."""
        if self.mqtt.connected:
            self.mqtt.disconnect()

    def connect(
        self,
        index: int | None = None,
        verify_ssl: bool = True,
        pahologger: bool = False,
    ) -> bool:
        """Connect to the cloud service endpoint

        Args:
            index (int | None, optional): Device number to connect to. Defaults to None.
            verify_ssl (bool, optional): Should we verify SSL certificate. Defaults to True.

        Returns:
            bool: True if connection was successful, otherwise False.
        """
        if not isinstance(index, type(None)):
            if index != self._dev_id:
                self._dev_id = index

        self._get_mac_address()
        self.product = {
            "mac_address": self.mac_address,
            "serial_number": self.serial_number,
            "setup_location": self.setup_location,
            "device": self._api.get_product_info(self.product_id),
            "created_at": self.created_at,
            "warranty": {
                "expires": self.warranty_expires_at,
                "registered": self.warranty_registered,
            },
            "sim": self.sim,
            "registered_at": self.registered_at,
        }

        self.product.update(
            {"board": self._api.get_board(self.product["device"]["board_id"])}
        )
        self.product.update(
            {
                "model": f'{self.product["device"]["default_name"]}{self.product["device"]["meters"]}'
            }
        )

        # Get blades statistics
        self.blades = Blades(data=self)

        # Get battery information
        self.battery = Battery(cycle_info=self)

        # setup MQTT handler
        self.mqtt = MQTT(
            self._worx_mqtt_client_id,
            protocol=mqtt.MQTTv311,
            topics=self.mqttdata.topics,
            name=self.name,
        )

        self.mqtt.on_message = self._forward_on_message
        self.mqtt.on_connect = self._on_connect
        self.mqtt.on_disconnect = self._on_disconnect
        self.mqtt.on_publish = self._on_published_message
        self.mqtt.on_connect_fail = self._on_connect_fail

        if pahologger:
            mqttlog = self._log.getChild("PahoMQTT")
            self.mqtt.on_log = self._on_log
            self.mqtt.enable_logger(mqttlog)
            self.mqttdata.logger = True

        try:
            with self._get_cert() as cert:
                self.mqtt.tls_set(certfile=cert)
        except ValueError:
            pass

        if not verify_ssl:
            self.mqtt.tls_insecure_set(True)

        self.mqtt.loop_start()
        self.mqtt.connect(self.mqttdata["endpoint"], port=8883, keepalive=600)

        self.mqttdata["messages"]["raw"].update(
            {
                "in": self.raw_messages_in,
                "out": self.raw_messages_out,
            }
        )
        self.mqttdata["messages"]["filtered"].update(
            {
                "in": self.messages_in,
                "out": self.messages_out,
            }
        )
        self.mqttdata["registered"] = self.mqtt_registered
        # Remove unwanted attribs
        for attr in UNWANTED_ATTRIBS:
            if hasattr(self, attr):
                delattr(self, attr)

        convert_to_time(self, self.time_zone, callback=self.update_attribute)

        return True

    @property
    def auth_result(self) -> bool:
        """Return current authentication result."""
        return self._auth_result

    def _authenticate(self):
        """Authenticate the user."""
        auth_data = self._api.auth()

        try:
            self._api.set_token(auth_data["access_token"])
            self._api.set_token_type(auth_data["token_type"])

            self._api.get_profile()
            profile = self._api.data
            if profile is None:
                return False
            self.mqttdata.update({"endpoint": profile["mqtt_endpoint"]})
            self._worx_mqtt_client_id = "android-" + self._api.uuid
        except:  # pylint: disable=bare-except
            return False

    @contextlib.contextmanager
    def _get_cert(self):
        """Cet current certificate."""

        certresp = self._api.get_cert()

        with pfx_to_pem(certresp["pkcs12"]) as pem_cert:
            yield pem_cert

    def _get_mac_address(self):
        """Get device MAC address for identification."""
        self._fetch()
        self.mqttdata.topics.update(
            {
                "out": self.mqtt_topics["command_out"],
                "in": self.mqtt_topics["command_in"],
            },
        )
        del self.mqtt_topics

    def _forward_on_message(
        self, client, userdata, message  # pylint: disable=unused-argument
    ):
        """MQTT callback method definition."""
        logger = self._log.getChild("mqtt.message_received")
        logger.debug("Received MQTT message for %s - processing data", self.name)
        self._fetch()
        self._mqtt_data = message.payload.decode("utf-8")
        self._decode_data(self._mqtt_data)
        if self._callback is not None:
            self._callback(self.product["serial_number"], "forward_on_message")

    def _decode_data(self, indata) -> None:
        """Decode incoming JSON data."""
        logger = self._log.getChild("decode_data")
        logger.debug("Data decoding for %s started", self.name)

        data = json.loads(indata)
        if "dat" in data:
            self.firmware = data["dat"]["fw"]
            self.rssi = data["dat"]["rsi"]
            self.status.update(data["dat"]["ls"])
            self.error.update(data["dat"]["le"])

            self.zone.index = data["dat"]["lz"]

            self.locked = bool(data["dat"]["lk"])

            # Get battery info if available
            if "bt" in data["dat"]:
                if len(self.battery) == 0:
                    self.battery = Battery(data["dat"]["bt"])
                else:
                    self.battery.set_data(data["dat"]["bt"])
            # Get device statistics if available
            if "st" in data["dat"]:
                self.statistics = Statistic(data["dat"]["st"])

            # Get orientation if available.
            if "dmp" in data["dat"]:
                self.orientation = Orientation(data["dat"]["dmp"])

            # Check for extra module availability
            if "modules" in data["dat"]:
                if "4G" in data["dat"]["modules"]:
                    self.gps = Location(
                        data["dat"]["modules"]["4G"]["gps"]["coo"][0],
                        data["dat"]["modules"]["4G"]["gps"]["coo"][1],
                    )

            # Get remaining rain delay if available
            if "rain" in data["dat"]:
                self.rainsensor.triggered = bool(str(data["dat"]["rain"]["s"]) == "1")
                self.rainsensor.remaining = int(data["dat"]["rain"]["cnt"])

        if "cfg" in data:
            self.updated = data["cfg"]["dt"] + " " + data["cfg"]["tm"]
            self.rainsensor.delay = int(data["cfg"]["rd"])

            # Fetch wheel torque
            if "tq" in data["cfg"]:
                self.capabilities.add(DeviceCapability.TORQUE)
                self.torque = data["cfg"]["tq"]

            # Fetch zone information
            if "mz" in data["cfg"]:
                self.zone.starting_point = data["cfg"]["mz"]
                self.zone.indicies = data["cfg"]["mzv"]

                # Map current zone to zone index
                self.zone.current = self.zone.indicies[self.zone.index]

            # Fetch main schedule
            if "sc" in data["cfg"]:
                if "ots" in data["cfg"]["sc"]:
                    self.capabilities.add(DeviceCapability.ONE_TIME_SCHEDULE)
                if "distm" in data["cfg"]["sc"]:
                    self.capabilities.add(DeviceCapability.PARTY_MODE)

                self.partymode_enabled = bool(str(data["cfg"]["sc"]["m"]) == "2")

                self.schedules["active"] = bool(str(data["cfg"]["sc"]["m"]) == "1")
                self.schedules["time_extension"] = data["cfg"]["sc"]["p"]

                sch_type = ScheduleType.PRIMARY
                schedule: dict = Schedule(sch_type)
                self.schedules[TYPE_TO_STRING[sch_type]] = schedule["days"]

                for day in range(0, len(data["cfg"]["sc"]["d"])):
                    self.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                        "start"
                    ] = data["cfg"]["sc"]["d"][day][0]
                    self.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                        "duration"
                    ] = data["cfg"]["sc"]["d"][day][1]
                    self.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                        "boundary"
                    ] = bool(data["cfg"]["sc"]["d"][day][2])

                    time_start = datetime.strptime(
                        self.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]]["start"],
                        "%H:%M",
                    )

                    if isinstance(
                        self.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                            "duration"
                        ],
                        type(None),
                    ):
                        self.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                            "duration"
                        ] = "0"

                    duration = int(
                        self.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                            "duration"
                        ]
                    )

                    duration = duration * (
                        1 + (int(self.schedules["time_extension"]) / 100)
                    )
                    end_time = time_start + timedelta(minutes=duration)

                    self.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                        "end"
                    ] = end_time.time().strftime("%H:%M")

            # Fetch secondary schedule
            if "dd" in data["cfg"]["sc"]:
                sch_type = ScheduleType.SECONDARY
                schedule = Schedule(sch_type)
                self.schedules[TYPE_TO_STRING[sch_type]] = schedule["days"]

                for day in range(0, len(data["cfg"]["sc"]["d"])):
                    self.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                        "start"
                    ] = data["cfg"]["sc"]["dd"][day][0]
                    self.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                        "duration"
                    ] = data["cfg"]["sc"]["dd"][day][1]
                    self.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                        "boundary"
                    ] = bool(data["cfg"]["sc"]["dd"][day][2])

                    time_start = datetime.strptime(
                        data["cfg"]["sc"]["dd"][day][0],
                        "%H:%M",
                    )

                    if isinstance(
                        self.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                            "duration"
                        ],
                        type(None),
                    ):
                        self.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                            "duration"
                        ] = "0"

                    duration = int(
                        self.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                            "duration"
                        ]
                    )

                    duration = duration * (
                        1 + (int(self.schedules["time_extension"]) / 100)
                    )
                    end_time = time_start + timedelta(minutes=duration)

                    self.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                        "end"
                    ] = end_time.time().strftime("%H:%M")

        convert_to_time(self, self.time_zone, callback=self.update_attribute)
        logger.debug("Data for %s was decoded", self.name)

    def _on_published_message(
        self, client, userdata, mid  # pylint: disable=unused-argument
    ):
        """Callback on message published."""
        logger = self._log.getChild("mqtt.published")
        logger.debug("MQTT message published to %s", self.name)

    def _on_log(self, client, userdata, level, buf):
        """Capture MQTT log messages."""
        logger = self._log.getChild("mqtt.log")
        logger.debug("MQTT log message for %s: %s", self.name, buf)

    def _on_connect_fail(self, client, userdata):
        """Called on connection failure."""
        logger = self._log.getChild("mqtt.log")
        logger.debug("MQTT connection for %s failed!", self.name)
        self.mqtt.connected = False
        if self._callback is not None:
            self._callback(self.product["serial_number"], "on_connect_fail")

    def _on_connect(
        self,
        client,
        userdata,
        flags,
        rc,  # pylint: disable=unused-argument,invalid-name
    ):
        """MQTT callback method."""
        logger = self._log.getChild("mqtt.connected")
        if rc == 0:
            topic = self.mqttdata.topics["out"]
            logger.debug(
                "MQTT connected for %s, subscribing to topic '%s'", self.name, topic
            )
            self.mqtt.connected = True
            client.subscribe(topic)

            if isinstance(self._mqtt_data, type(None)):
                logger.debug("MQTT chached data not found - requesting")
                mqp = self.mqtt.send()
                mqp.wait_for_publish(10)
        else:
            self.mqtt.connected = False
            if self._callback is not None:
                self._callback(self.product["serial_number"], "on_connect")

            raise MQTTException(connack_string(rc))

    def _on_disconnect(
        self,
        client,
        userdata,
        rc,  # pylint: disable=unused-argument,invalid-name
    ):
        """MQTT callback method."""
        if rc > 0:
            if self.mqtt.connected:
                logger = self._log.getChild("mqtt.disconnected")
                logger.debug(
                    "MQTT connection for %s was lost! (%s)", self.name, error_string(rc)
                )
                if self._callback is not None:
                    self._callback(self.product["serial_number"], "on_disconnect")

            self.mqtt.connected = False

    def _fetch(self) -> None:
        """Fetch base API information."""
        self._api.get_products()
        products = self._api.data

        accessories = None
        for attr, val in products[self._dev_id].items():
            if attr == "accessories":
                accessories = val
            else:
                setattr(self, str(attr), val)

        if not accessories is None:
            self.accessories = []
            for key in accessories:
                self.accessories.append(key)

    def enumerate(self) -> int:
        """Fetch number of devices connected to the account.

        Returns:
            int: Represents the number of available devices in the account, starting from 0 as the first devices associated with the account.
        """
        self._api.get_products()
        products = self._api.data
        self._log.debug(
            "Enumeration found %s devices on account %s", len(products), self._username
        )
        return len(products)

    # Service calls starts here
    def send(self, data: str) -> None:
        """Send raw JSON data to the device.

        Args:
            data (str): Data to be sent, formatted as a valid JSON object.

        Raises:
            OfflineError: Raised if the device isn't online.
        """
        if self.online:
            self._log.debug("Sending %s to %s", data, self.name)
            self.mqtt.send(data)
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def update(self) -> None:
        """Retrive current device status."""
        status = self._api.get_status(self.product["serial_number"])
        status = str(status).replace("'", '"')
        self._raw = status

        self._decode_data(status)

    def start(self) -> None:
        """Start mowing task

        Raises:
            OfflineError: Raised if the device is offline.
        """
        if self.online:
            logger = self._log.getChild("command")
            logger.debug("Sending START command to %s", self.name)
            self.mqtt.command(Command.START)
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def pause(self) -> None:
        """Pause the mowing task

        Raises:
            OfflineError: Raised if the device is offline.
        """
        if self.online:
            logger = self._log.getChild("command")
            logger.debug("Sending PAUSE command to %s", self.name)
            self.mqtt.command(Command.PAUSE)
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def home(self) -> None:
        """Stop the current task and go home.
        If the knifes was turned on when this is called, it will return home with knifes still turned on.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        if self.online:
            logger = self._log.getChild("command")
            logger.debug("Sending HOME command to %s", self.name)
            self.mqtt.command(Command.HOME)
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def zonetraining(self) -> None:
        """Start the zone training task.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        if self.online:
            logger = self._log.getChild("command")
            logger.debug("Sending ZONETRAINING command to %s", self.name)
            self.mqtt.command(Command.ZONETRAINING)
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def lock(self, enabled: bool) -> None:
        """Set the device locked state.

        Args:
            enabled (bool): True will lock the device, False will unlock the device.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        if self.online:
            if enabled:
                logger = self._log.getChild("command")
                logger.debug("Sending LOCK command to %s", self.name)
                self.mqtt.command(Command.LOCK)
            else:
                logger = self._log.getChild("command")
                logger.debug("Sending UNLOCK command to %s", self.name)
                self.mqtt.command(Command.UNLOCK)
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def restart(self):
        """Reboot the device baseboard.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        if self.online:
            logger = self._log.getChild("command")
            logger.debug("Sending RESTART command to %s", self.name)
            self.mqtt.command(Command.RESTART)
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def safehome(self):
        """Stop and go home with the blades off

        Raises:
            OfflineError: Raised if the device is offline.
        """
        if self.online:
            logger = self._log.getChild("command")
            logger.debug("Sending SAFEHOME command to %s", self.name)
            self.mqtt.command(Command.SAFEHOME)
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def raindelay(self, rain_delay: str | int) -> None:
        """Set new rain delay.

        Args:
            rain_delay (str | int): Rain delay in minutes.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        if self.online:
            if not isinstance(rain_delay, str):
                rain_delay = str(rain_delay)
            msg = f'"rd": {rain_delay}'
            self.mqtt.send(msg)
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def toggle_schedule(self, enable: bool) -> None:
        """Turn on or off the schedule.

        Args:
            enable (bool): True is enabling the schedule, Fasle is disabling the schedule.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        if self.online:
            if enable:
                msg = '{"sc": {"m": 1}}'
            else:
                msg = '{"sc": {"m": 0}}'

            self.mqtt.send(msg)
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def toggle_partymode(self, enabled: bool) -> None:
        """Turn on or off the partymode.

        Args:
            enable (bool): True is enabling partymode, Fasle is disabling partymode.

        Raises:
            NoPartymodeError: Raised if the device does not support partymode.
            OfflineError: Raised if the device is offline.
        """
        if self.online and self.capabilities.check(DeviceCapability.PARTY_MODE):
            if enabled:
                msg = '{"sc": {"m": 2, "distm": 0}}'
            else:
                msg = '{"sc": {"m": 1, "distm": 0}}'

            self.mqtt.send(msg)
        elif not self.capabilities.check(DeviceCapability.PARTY_MODE):
            raise NoPartymodeError("This device does not support Partymode")
        elif not self.online:
            raise OfflineError("The device is currently offline, no action was sent.")

    def ots(self, boundary: bool, runtime: str | int) -> None:
        """Start a One-Time-Schedule task

        Args:
            boundary (bool): If True the device will start the task cutting the edge.
            runtime (str | int): Minutes to run the task before returning to dock.

        Raises:
            NoOneTimeScheduleError: OTS is not supported by the device.
            OfflineError: Raised when the device is offline.
        """
        if self.online and self.capabilities.check(DeviceCapability.ONE_TIME_SCHEDULE):
            if not isinstance(runtime, int):
                runtime = int(runtime)

            raw = {"sc": {"ots": {"bc": int(boundary), "wtm": runtime}}}
            self.mqtt.send(json.dumps(raw))
        elif not self.capabilities.check(DeviceCapability.ONE_TIME_SCHEDULE):
            raise NoOneTimeScheduleError(
                "This device does not support Edgecut-on-demand"
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def setzone(self, zone: str | int) -> None:
        """Set zone to be mowed when next mowing task is started.

        Args:
            zone (str | int): Zone to mow, valid possibilities are a number from 1 to 4.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        if self.online:
            if not isinstance(zone, int):
                zone = int(zone)

            current = self.zone_probability
            new_zones = current
            while not new_zones[self.mowing_zone] == zone:
                tmp = []
                tmp.append(new_zones[9])
                for i in range(0, 9):
                    tmp.append(new_zones[i])
                new_zones = tmp

            raw = {"mzv": new_zones}
            self.mqtt.send(json.dumps(raw))
        else:
            raise OfflineError("The device is currently offline, no action was sent.")


@contextlib.contextmanager
def pfx_to_pem(pfx_data):
    """Decrypts the .pfx file to be used with requests."""
    with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as t_pem:
        f_pem = open(t_pem.name, "wb")
        p12 = OpenSSL.crypto.load_pkcs12(base64.b64decode(pfx_data), "")
        f_pem.write(
            OpenSSL.crypto.dump_privatekey(
                OpenSSL.crypto.FILETYPE_PEM, p12.get_privatekey()
            )
        )
        f_pem.write(
            OpenSSL.crypto.dump_certificate(
                OpenSSL.crypto.FILETYPE_PEM, p12.get_certificate()
            )
        )
        certauth = p12.get_ca_certificates()
        if certauth is not None:
            for cert in certauth:
                f_pem.write(
                    OpenSSL.crypto.dump_certificate(OpenSSL.crypto.FILETYPE_PEM, cert)
                )
        f_pem.close()
        yield t_pem.name
