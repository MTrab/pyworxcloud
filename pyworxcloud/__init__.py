"""pyWorxCloud definition."""
from __future__ import annotations

import base64
import contextlib
import json
import logging
import sys
import tempfile
import time
from datetime import datetime, timedelta

import OpenSSL.crypto
import paho.mqtt.client as mqtt

from .clouds import CloudType
from .day_map import DAY_MAP
from .exceptions import (
    AuthorizationError,
    NoOneTimeScheduleError,
    NoPartymodeError,
    OfflineError,
)
from .api import LandroidCloudAPI
from .schedules import TYPE_TO_STRING, Schedule, ScheduleType

from .utils import Blades, Battery, Capability, DeviceCapability, Location, Orientation

_LOGGER = logging.getLogger(__name__)

if sys.version_info < (3, 10, 0):
    sys.exit("The pyWorxcloud module requires Python 3.10.0 or later")


class WorxCloud(object):
    """
    Worx by Landroid Cloud connector.

    Used for handling API connection to Worx, Kress and Landxcape devices which are cloud connected.

    This uses a reverse engineered API protocol, so no guarantee that this will keep working.
    There are no public available API documentation available.
    """

    wait = True

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
        self._worx_mqtt_endpoint = None

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

        self._auth_result = False
        self._callback = None  # Callback used when data arrives from cloud
        self._dev_id = index
        self._mqtt = None
        self._raw = None
        self._save_zones = None
        self._verify_ssl = verify_ssl

        # Set default attribute values
        ###############################
        self.accessories = None
        self.battery = Battery()
        self.blades = Blades()
        self.board = []
        self.error = None
        self.firmware = None
        self.gps = Location()
        self.locked = False
        self.mac_address = None
        self.model = "Unknown"
        self.mqtt_in = None
        self.mqtt_out = None
        self.mqtt_topics = {}
        self.online = False
        self.orientation = Orientation([0, 0, 0])
        self.capabilities = Capability()
        self.capability_ots = False
        self.capability_partymode = False
        self.partymode_enabled = False
        self.product = []
        self.rain_delay = None
        self.rain_delay_time_remaining = None
        self.rain_sensor_triggered = None
        self.rssi = None
        self.schedule_mower_active = False
        self.schedule_variation = None
        self.schedules = {}
        self.serial_number = None
        self.status = None
        self.status_description = None
        self.torque = None
        self.capability_torque = False
        self.updated = None
        self.work_time = 0
        self.zone_current = 0
        self.zone_index = 0
        self.zone_indicies = []
        self.zone_start = []

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
        auth = self._authenticate()
        if auth is False:
            self._auth_result = False
            raise AuthorizationError("Unauthorized")

        self._auth_result = True

        return True

    def set_callback(self, callback) -> None:
        """Set callback which is called when data is received.

        Args:
            callback (function): Function to be called.
        """
        self._callback = callback

    def disconnect(self) -> None:
        """Close API connections."""
        if hasattr(self._mqtt, "disconnect"):
            self._mqtt.disconnect()

    def connect(self, index: int | None = None, verify_ssl: bool = True) -> bool:
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
        self.product = self._api.get_product_info(self.product_id)
        self.model = f'{self.product["default_name"]}{self.product["meters"]}'

        self._mqtt = mqtt.Client(self._worx_mqtt_client_id, protocol=mqtt.MQTTv311)

        self._mqtt.on_message = self._forward_on_message
        self._mqtt.on_connect = self._on_connect

        try:
            with self._get_cert() as cert:
                self._mqtt.tls_set(certfile=cert)
        except ValueError:
            pass

        if not verify_ssl:
            self._mqtt.tls_insecure_set(True)

        conn_res = self._mqtt.connect(
            self._worx_mqtt_endpoint, port=8883, keepalive=600
        )
        if conn_res:
            return False

        self._mqtt.loop_start()
        mqp = self._mqtt.publish(self.mqtt_in, "{}", qos=0, retain=False)
        while not mqp.is_published:
            time.sleep(0.1)

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
            self._worx_mqtt_endpoint = profile["mqtt_endpoint"]

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
        self.mqtt_out = self.mqtt_topics["command_out"]
        self.mqtt_in = self.mqtt_topics["command_in"]
        self.board = self._api.get_board(self.mqtt_out.split("/")[0])

    def _forward_on_message(
        self, client, userdata, message
    ):  # pylint: disable=unused-argument
        """MQTT callback method definition."""
        json_message = message.payload.decode("utf-8")
        self._decode_data(json_message)

        if self._callback is not None:
            self._callback()

    def _decode_data(self, indata) -> None:
        """Decode incoming JSON data."""
        data = json.loads(indata)
        if "dat" in data:
            self.firmware = data["dat"]["fw"]
            self.rssi = data["dat"]["rsi"]
            self.status = data["dat"]["ls"]
            self.error = data["dat"]["le"]

            self.zone_index = data["dat"]["lz"]

            self.locked = bool(data["dat"]["lk"])

            # Get battery info if available
            if "bt" in data["dat"]:
                self.battery = Battery(data["dat"]["bt"])

            # Get blade data if available
            if "st" in data["dat"]:
                self.blades = Blades(data["dat"]["st"])

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
                self.rain_delay_time_remaining = data["dat"]["rain"]["cnt"]
                self.rain_sensor_triggered = bool(str(data["dat"]["rain"]["s"]) == "1")

        if "cfg" in data:
            self.updated = data["cfg"]["tm"] + " " + data["cfg"]["dt"]
            self.rain_delay = data["cfg"]["rd"]
            self.serial = data["cfg"]["sn"]

            # Fetch wheel torque
            if "tq" in data["cfg"]:
                self.capabilities.add(DeviceCapability.TORQUE)
                self.torque = data["cfg"]["tq"]

            # Fetch zone information
            if "mz" in data["cfg"]:
                self.zone_start = data["cfg"]["mz"]
                self.zone_indicies = data["cfg"]["mzv"]

                # Map current zone to zone index
                self.zone_current = self.zone_indicies[self.zone_index]

            # Fetch main schedule
            if "sc" in data["cfg"]:
                if "ots" in data["cfg"]["sc"]:
                    self.capabilities.add(DeviceCapability.ONE_TIME_SCHEDULE)
                if "distm" in data["cfg"]["sc"]:
                    self.capabilities.add(DeviceCapability.PARTY_MODE)

                self.schedule_mower_active = bool(str(data["cfg"]["sc"]["m"]) == "1")
                self.partymode_enabled = bool(str(data["cfg"]["sc"]["m"]) == "2")

                self.schedule_variation = data["cfg"]["sc"]["p"]

                sch_type = ScheduleType.PRIMARY
                schedule = Schedule(sch_type).todict
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

                    duration = duration * (1 + (int(self.schedule_variation) / 100))
                    end_time = time_start + timedelta(minutes=duration)

                    self.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                        "end"
                    ] = end_time.time().strftime("%H:%M")

            # Fetch secondary schedule
            if "dd" in data["cfg"]["sc"]:
                sch_type = ScheduleType.SECONDARY
                schedule = Schedule(sch_type).todict
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

                    duration = duration * (1 + (int(self.schedule_variation) / 100))
                    end_time = time_start + timedelta(minutes=duration)

                    self.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[day]][
                        "end"
                    ] = end_time.time().strftime("%H:%M")

        self.wait = False

    def _on_connect(
        self, client, userdata, flags, rc
    ):  # pylint: disable=unused-argument,invalid-name
        """MQTT callback method."""
        client.subscribe(self.mqtt_out)

    def _fetch(self) -> None:
        """Fetch devices."""
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
            self._mqtt.publish(self.mqtt_in, data, qos=0, retain=False)
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def update(self) -> None:
        """Retrive current device status."""
        status = self._api.get_status(self.serial_number)
        status = str(status).replace("'", '"')
        self._raw = status

        self._decode_data(status)

    def start(self) -> None:
        """Start mowing task

        Raises:
            OfflineError: Raised if the device is offline.
        """
        if self.online:
            self._mqtt.publish(self.mqtt_in, '{"cmd":1}', qos=0, retain=False)
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def pause(self) -> None:
        """Pause the mowing task

        Raises:
            OfflineError: Raised if the device is offline.
        """
        if self.online:
            self._mqtt.publish(self.mqtt_in, '{"cmd":2}', qos=0, retain=False)
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def home(self) -> None:
        """Stop the current task and go home.
        If the knifes was turned on when this is called, it will return home with knifes still turned on.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        if self.online:
            self._mqtt.publish(self.mqtt_in, '{"cmd":3}', qos=0, retain=False)
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def zonetraining(self) -> None:
        """Start the zone training task.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        if self.online:
            self._mqtt.publish(self.mqtt_in, '{"cmd":4}', qos=0, retain=False)
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
                self._mqtt.publish(self.mqtt_in, '{"cmd":5}', qos=0, retain=False)
            else:
                self._mqtt.publish(self.mqtt_in, '{"cmd":6}', qos=0, retain=False)
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def restart(self):
        """Reboot the device baseboard.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        if self.online:
            self._mqtt.publish(self.mqtt_in, '{"cmd":7}', qos=0, retain=False)
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def safehome(self):
        """Stop and go home with the blades off

        Raises:
            OfflineError: Raised if the device is offline.
        """
        if self.online:
            self._mqtt.publish(self.mqtt_in, '{"cmd":9}', qos=0, retain=False)
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
            self._mqtt.publish(self.mqtt_in, msg, qos=0, retain=False)
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
                self._mqtt.publish(self.mqtt_in, msg, qos=0, retain=False)
            else:
                msg = '{"sc": {"m": 0}}'
                self._mqtt.publish(self.mqtt_in, msg, qos=0, retain=False)
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
                self._mqtt.publish(self.mqtt_in, msg, qos=0, retain=False)
            else:
                msg = '{"sc": {"m": 1, "distm": 0}}'
                self._mqtt.publish(self.mqtt_in, msg, qos=0, retain=False)
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
            _LOGGER.debug(json.dumps(raw))
            self._mqtt.publish(self.mqtt_in, json.dumps(raw), qos=0, retain=False)
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
            self._mqtt.publish(self.mqtt_in, json.dumps(raw), qos=0, retain=False)
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
