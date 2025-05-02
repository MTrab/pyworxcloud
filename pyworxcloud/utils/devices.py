"""Class for handling device info and states."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from pyworxcloud.day_map import DAY_MAP

from ..const import UNWANTED_ATTRIBS
from ..exceptions import APIException, InvalidDataDecodeException
from ..helpers import convert_to_time
from .battery import Battery
from .blades import Blades
from .capability import Capability, DeviceCapability
from .firmware import Firmware
from .landroid_class import LDict
from .lawn import Lawn
from .location import Location
from .orientation import Orientation
from .rainsensor import Rainsensor
from .schedules import TYPE_TO_STRING, Schedule, ScheduleType, Weekdays
from .state import States, StateType
from .statistics import Statistic
from .warranty import Warranty
from .zone import Zone

LOGGER = logging.getLogger(__name__)


class DeviceHandler(LDict):
    """DeviceHandler for Landroid Cloud devices."""

    __is_decoded: bool = True
    __raw_data: str = None
    __json_data: str = None

    def __init__(
        self,
        api: Any = None,
        mower: Any = None,
        tz: str | None = None,
        decode: bool = True,
    ) -> dict:
        """Initialize the object."""
        super().__init__()

        self._api = api
        self.mower = mower
        self._tz = tz
        self._decode = decode

        self.battery = Battery()
        self.blades = Blades()
        self.error = States(StateType.ERROR)
        self.orientation = Orientation([0, 0, 0])
        self.capabilities = Capability()
        self.rainsensor = Rainsensor()
        self.status = States()
        self.zone = Zone()
        self.warranty = Warranty()
        self.firmware = Firmware()
        self.schedules = Schedule()
        self.statistics = Statistic([])
        self.in_topic = None
        self.out_topic = None

        if not isinstance(mower, type(None)) and not isinstance(api, type(None)):
            self.__mapinfo(api, mower)

    @property
    def raw_data(self) -> str:
        """Returns current raw dataset."""
        return self.__raw_data

    @property
    def json_data(self) -> str:
        """Returns current dataset as JSON."""
        return self.__json_data

    @raw_data.setter
    def raw_data(self, value: str) -> None:
        """Set new MQTT data."""
        self.__is_decoded = False
        self.__raw_data = value
        try:
            self.__json_data = json.loads(value)
        except:  # pylint: disable=bare-except
            pass  # Just continue if we couldn't decode the data

        self.decode_data()

    @property
    def is_decoded(self) -> bool:
        """Returns true if latest dataset was decoded and handled."""
        return self.__is_decoded

    @is_decoded.setter
    def is_decoded(self, value: bool) -> None:
        """Set decoded flag when dataset was decoded and handled."""
        self.__is_decoded = value

    def __mapinfo(self, api: Any, data: Any) -> None:
        """Map information from API."""

        if isinstance(data, type(None)) or isinstance(api, type(None)):
            raise APIException(
                "Either 'data' or 'api' object was missing, no data was mapped!"
            )

        for attr, val in data.items():
            setattr(self, str(attr), val)

        if not "time_zone" in data:
            data["time_zone"] = "UTC"

        self.battery = Battery(data)
        self.blades = Blades(data)
        self.error = States(StateType.ERROR)
        self.orientation = Orientation([0, 0, 0])
        self.capabilities = Capability(data)
        self.rainsensor = Rainsensor()
        self.status = States()
        self.zone = Zone(data)
        self.warranty = Warranty(data)
        self.firmware = Firmware(data)
        self.schedules = Schedule(data)
        self.statistics = Statistic([])
        self.in_topic = data["mqtt_topics"]["command_in"]
        self.out_topic = data["mqtt_topics"]["command_out"]

        if data in ["lawn_perimeter", "lawn_size"]:
            self.lawn = Lawn(data["lawn_perimeter"], data["lawn_size"])

        self.name = data["name"]
        self.model = str.format(
            "{} ({})", data["model"]["friendly_name"], data["model"]["code"]
        )

        self.mac_address = None
        self.protocol = 0
        self.time_zone = None

        for attr in UNWANTED_ATTRIBS:
            if hasattr(self, attr):
                delattr(self, attr)

        if self._decode:
            self.decode_data()
            self.is_decoded = True

    def decode_data(self) -> None:
        """Decode incoming JSON data."""
        invalid_data = False
        self.is_decoded = False

        logger = LOGGER.getChild("decode_data")
        logger.debug("Data decoding for %s started", self.name)

        if self.json_data:
            logger.debug("Found JSON decoded data: %s", self.json_data)
            data = self.json_data
        elif self.raw_data:
            logger.debug("Found raw data: %s", self.raw_data)
            data = self.raw_data
        elif (
            not isinstance(self.last_status, type(None))
            and "payload" in self.last_status
        ):
            data = self.last_status["payload"]
        else:
            self.is_decoded = True
            logger.debug("No valid data was found, skipping update for %s", self.name)
            return

        if isinstance(self.capabilities, list):
            setattr(self, "api_capabilities", getattr(self, "capabilities"))
            self.capabilities = Capability(data)

        mower = self.mower
        self.protocol = mower["protocol"]

        if "dat" in data:
            mower["last_status"]["payload"]["dat"] = data["dat"]
            if "uuid" in data["dat"]:
                self.uuid = data["dat"]["uuid"]

            if isinstance(self.mac_address, type(None)):
                self.mac_address = (
                    data["dat"]["mac"] if "mac" in data["dat"] else "__UUID__"
                )

            try:
                # Get wifi signal strength
                if "rsi" in data["dat"]:
                    self.rssi = data["dat"]["rsi"]

                # Get status code
                if "ls" in data["dat"]:
                    self.status.update(data["dat"]["ls"])

                # Get error code
                if "le" in data["dat"]:
                    self.error.update(data["dat"]["le"])

                # Get zone index
                self.zone.index = data["dat"]["lz"] if "lz" in data["dat"] else 0

                # Get device lock state
                self.locked = bool(data["dat"]["lk"]) if "lk" in data["dat"] else None
                mower["locked"] = self.locked

                # Get battery info if available
                if "bt" in data["dat"]:
                    if len(self.battery) == 0:
                        self.battery = Battery(data["dat"]["bt"])
                    else:
                        self.battery.set_data(data["dat"]["bt"])
                # Get device statistics if available
                if "st" in data["dat"]:
                    self.statistics = Statistic(data["dat"]["st"])

                    if len(self.blades) != 0:
                        self.blades.set_data(data["dat"]["st"])

                # Get orientation if available.
                if "dmp" in data["dat"]:
                    self.orientation = Orientation(data["dat"]["dmp"])

                # Check for extra module availability
                if "modules" in data["dat"]:
                    if "4G" in data["dat"]["modules"]:
                        if "gps" in data["dat"]["modules"]["4G"]:
                            self.gps = Location(
                                data["dat"]["modules"]["4G"]["gps"]["coo"][0],
                                data["dat"]["modules"]["4G"]["gps"]["coo"][1],
                            )

                # Get remaining rain delay if available
                if "rain" in data["dat"]:
                    self.rainsensor.triggered = bool(
                        str(data["dat"]["rain"]["s"]) == "1"
                    )
                    self.rainsensor.remaining = int(data["dat"]["rain"]["cnt"])

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

            self.updated = date
            self.rainsensor.delay = int(data["cfg"]["rd"])

            # Fetch wheel torque
            if "tq" in data["cfg"]:
                self.capabilities.add(DeviceCapability.TORQUE)
                self.torque = data["cfg"]["tq"]

            # Fetch zone information
            if "mz" in data["cfg"] and "mzv" in data["cfg"]:
                self.zone.starting_point = data["cfg"]["mz"]
                self.zone.indicies = data["cfg"]["mzv"]

                # Map current zone to zone index
                self.zone.current = self.zone.indicies[self.zone.index]

            # Fetch main schedule
            if "sc" in data["cfg"]:
                if "ots" in data["cfg"]["sc"]:
                    self.capabilities.add(DeviceCapability.ONE_TIME_SCHEDULE)
                    self.capabilities.add(DeviceCapability.EDGE_CUT)
                if "m" in data["cfg"]["sc"] or "enabled" in data["cfg"]["sc"]:
                    self.capabilities.add(DeviceCapability.PARTY_MODE)
                    self.partymode_enabled = (
                        bool(str(data["cfg"]["sc"]["m"]) == "2")
                        if self.protocol == 0
                        else bool(str(data["cfg"]["sc"]["enabled"]) == "0")
                    )
                    self.schedules["active"] = (
                        bool(str(data["cfg"]["sc"]["m"]) in ["1", "2"])
                        if self.protocol == 0
                        else bool(str(data["cfg"]["sc"]["enabled"]) == "0")
                    )

                self.schedules["time_extension"] = (
                    data["cfg"]["sc"]["p"] if self.protocol == 0 else "0"
                )

                sch_type = ScheduleType.PRIMARY
                self.schedules.update({TYPE_TO_STRING[sch_type]: Weekdays()})

                try:
                    for day in range(
                        0,
                        (
                            len(data["cfg"]["sc"]["d"])
                            if self.protocol == 0
                            else len(data["cfg"]["sc"]["slots"])
                        ),
                    ):
                        dayOfWeek = (  # pylint: disable=invalid-name
                            day
                            if self.protocol == 0
                            else data["cfg"]["sc"]["slots"][day]["d"]
                        )
                        self.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[dayOfWeek]][
                            "start"
                        ] = (
                            data["cfg"]["sc"]["d"][day][0]
                            if self.protocol == 0
                            else (
                                datetime.strptime("00:00", "%H:%M")
                                + timedelta(
                                    minutes=data["cfg"]["sc"]["slots"][day]["s"]
                                )
                            ).strftime("%H:%M")
                        )
                        self.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[dayOfWeek]][
                            "duration"
                        ] = (
                            data["cfg"]["sc"]["d"][day][1]
                            if self.protocol == 0
                            else data["cfg"]["sc"]["slots"][day]["t"]
                        )
                        self.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[dayOfWeek]][
                            "boundary"
                        ] = (
                            bool(data["cfg"]["sc"]["d"][day][2])
                            if self.protocol == 0
                            else (
                                bool(data["cfg"]["sc"]["slots"][day]["cfg"]["cut"]["b"])
                                if "b" in data["cfg"]["sc"]["slots"][day]["cfg"]["cut"]
                                else None
                            )
                        )

                        time_start = datetime.strptime(
                            self.schedules[TYPE_TO_STRING[sch_type]][
                                DAY_MAP[dayOfWeek]
                            ]["start"],
                            "%H:%M",
                        )

                        if isinstance(
                            self.schedules[TYPE_TO_STRING[sch_type]][
                                DAY_MAP[dayOfWeek]
                            ]["duration"],
                            type(None),
                        ):
                            self.schedules[TYPE_TO_STRING[sch_type]][
                                DAY_MAP[dayOfWeek]
                            ]["duration"] = "0"

                        duration = int(
                            self.schedules[TYPE_TO_STRING[sch_type]][
                                DAY_MAP[dayOfWeek]
                            ]["duration"]
                        )

                        duration = duration * (
                            1 + (int(self.schedules["time_extension"]) / 100)
                        )
                        end_time = time_start + timedelta(minutes=duration)

                        self.schedules[TYPE_TO_STRING[sch_type]][DAY_MAP[dayOfWeek]][
                            "end"
                        ] = end_time.time().strftime("%H:%M")
                except KeyError:
                    pass

                # Fetch secondary schedule
                try:
                    if "dd" in data["cfg"]["sc"]:
                        sch_type = ScheduleType.SECONDARY
                        self.schedules.update({TYPE_TO_STRING[sch_type]: Weekdays()})

                        for day in range(0, len(data["cfg"]["sc"]["dd"])):
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
                except KeyError:
                    pass

                # Check for addon modules
                if "modules" in data["cfg"]:
                    if "DF" in data["cfg"]["modules"]:
                        self.capabilities.add(DeviceCapability.OFF_LIMITS)
                        self.offlimit = bool(
                            str(data["cfg"]["modules"]["DF"]["cut"]) == "1"
                        )
                        self.offlimit_shortcut = bool(
                            str(data["cfg"]["modules"]["DF"]["fh"]) == "1"
                        )

                    if "US" in data["cfg"]["modules"]:
                        self.capabilities.add(DeviceCapability.ACS)
                        self.acs_enabled = bool(
                            str(data["cfg"]["modules"]["US"]["enabled"]) == "1"
                        )

            self.schedules.update_progress_and_next(
                tz=(
                    self._tz if not isinstance(self._tz, type(None)) else self.time_zone
                )
            )
            # except TypeError:
            #     invalid_data = True
            # except KeyError:
            #     invalid_data = True

        convert_to_time(self.name, self, self._tz, callback=self.update_attribute)

        mower["last_status"]["timestamp"] = self.updated

        self.is_decoded = True
        logger.debug("Data for %s was decoded", self.name)
        logger.debug("Device object:\n%s", vars(self))

        if invalid_data:
            raise InvalidDataDecodeException()

    def update_attribute(self, device: str, attr: str, key: str, value: Any) -> None:
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
