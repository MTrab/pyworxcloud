"""Class for handling device info and states."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

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
from .schedule_mapper import ScheduleParser
from .schedules import Schedule
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
        self.raw_cfg: dict[str, Any] | None = None
        self.raw_dat: dict[str, Any] | None = None
        self.module_config: dict[str, Any] | None = None
        self.module_status: dict[str, Any] | None = None
        self.raindelay_active: bool | None = None
        self.last_activity: int | None = None
        self.offlimit: bool | None = None
        self.offlimit_shortcut: bool | None = None
        self.acs_enabled: bool | None = None
        self.partymode_enabled: bool | None = None

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

        self.name = (
            data["name"] if not isinstance(data["name"], type(None)) else "No Name"
        )
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

        payload = self._resolve_payload()
        if payload is None:
            self.is_decoded = True
            logger.debug("No valid data was found, skipping update for %s", self.name)
            return

        if not isinstance(payload, dict):
            logger.debug(
                "Payload for %s is not a dict (type=%s)", self.name, type(payload)
            )
            raise InvalidDataDecodeException()

        if isinstance(self.capabilities, list):
            setattr(self, "api_capabilities", getattr(self, "capabilities"))
            self.capabilities = Capability(payload)

        mower = self.mower
        self.protocol = mower["protocol"]

        dat_payload = payload.get("dat")
        if isinstance(dat_payload, dict):
            mower["last_status"]["payload"]["dat"] = dat_payload
            try:
                self._map_dat(dat_payload)
            except (TypeError, ValueError):
                invalid_data = True
            finally:
                self.last_activity = dat_payload.get("act")

            self.raw_dat = dat_payload
            self.module_status = dat_payload.get("modules", {})

        cfg_payload = payload.get("cfg")
        if isinstance(cfg_payload, dict):
            mower["last_status"]["payload"]["cfg"] = cfg_payload
            self.raw_cfg = cfg_payload
            try:
                self._map_cfg(cfg_payload)
            except (TypeError, ValueError):
                invalid_data = True

        self.updated = self._determine_updated_at(cfg_payload, dat_payload)

        self.schedules.update_progress_and_next(
            tz=self._tz if not isinstance(self._tz, type(None)) else self.time_zone
        )

        convert_to_time(self.name, self, self._tz, callback=self.update_attribute)

        mower["last_status"]["timestamp"] = self.updated

        self.is_decoded = True
        logger.debug("Data for %s was decoded", self.name)

        if invalid_data:
            raise InvalidDataDecodeException()

    def _resolve_payload(self) -> dict[str, Any] | None:
        """Return the most recent payload dict (JSON/raw/last_status)."""
        if self.json_data:
            return self.json_data

        if self.raw_data:
            if isinstance(self.raw_data, dict):
                return self.raw_data
            try:
                return json.loads(self.raw_data)
            except json.JSONDecodeError:
                pass

        last_status = getattr(self, "last_status", None)
        if isinstance(last_status, dict) and "payload" in last_status:
            return last_status["payload"]

        return None

    def _map_dat(self, dat_payload: dict[str, Any]) -> None:
        """Map realtime data fields from a payload."""
        if "uuid" in dat_payload:
            self.uuid = dat_payload["uuid"]

        if isinstance(self.mac_address, type(None)):
            self.mac_address = dat_payload.get("mac", "__UUID__")

        if "rsi" in dat_payload:
            self.rssi = dat_payload["rsi"]

        if "ls" in dat_payload:
            self.status.update(dat_payload["ls"])

        if "le" in dat_payload:
            self.error.update(dat_payload["le"])

        self.zone.index = dat_payload.get("lz", self.zone.index)

        if "lk" in dat_payload:
            self.locked = bool(dat_payload["lk"])
        else:
            self.locked = None

        try:
            self.mower["locked"] = self.locked
        except (TypeError, KeyError):
            pass

        if "bt" in dat_payload:
            if len(self.battery) == 0:
                self.battery = Battery(dat_payload["bt"])
            else:
                self.battery.set_data(dat_payload["bt"])

        if "st" in dat_payload:
            self.statistics = Statistic(dat_payload["st"])
            if len(self.blades) != 0:
                self.blades.set_data(dat_payload["st"])

        if "dmp" in dat_payload:
            self.orientation = Orientation(dat_payload["dmp"])

        modules = dat_payload.get("modules")
        if isinstance(modules, dict):
            if "4G" in modules:
                gps = modules["4G"].get("gps")
                if isinstance(gps, dict) and "coo" in gps:
                    self.gps = Location(gps["coo"][0], gps["coo"][1])

        rain = dat_payload.get("rain")
        if isinstance(rain, dict):
            triggered = str(rain.get("s")) == "1"
            self.rainsensor.triggered = triggered
            self.rainsensor.remaining = int(rain.get("cnt", 0))
            self.raindelay_active = triggered

    def _map_cfg(self, cfg_payload: dict[str, Any]) -> None:
        """Map configuration data including schedules."""
        rd_value = cfg_payload.get("rd")
        self.rainsensor.delay = int(rd_value) if rd_value is not None else 0

        if "tq" in cfg_payload:
            self.capabilities.add(DeviceCapability.TORQUE)
            self.torque = cfg_payload["tq"]

        if "mz" in cfg_payload and "mzv" in cfg_payload:
            self.zone.starting_point = cfg_payload["mz"]
            self.zone.indicies = cfg_payload["mzv"]
            self.zone.current = self.zone.indicies[self.zone.index]

        modules_cfg = cfg_payload.get("modules")
        if isinstance(modules_cfg, dict):
            self.module_config = modules_cfg
            if "DF" in modules_cfg:
                self.capabilities.add(DeviceCapability.OFF_LIMITS)
                self.offlimit = bool(str(modules_cfg["DF"].get("cut")) == "1")
                self.offlimit_shortcut = bool(str(modules_cfg["DF"].get("fh")) == "1")
            if "US" in modules_cfg:
                self.capabilities.add(DeviceCapability.ACS)
                self.acs_enabled = bool(str(modules_cfg["US"].get("enabled")) == "1")

        sc_payload = cfg_payload.get("sc")
        if not isinstance(sc_payload, dict):
            return

        result = ScheduleParser(sc_payload, self.protocol).parse()

        if "m" in sc_payload or "enabled" in sc_payload:
            self.capabilities.add(DeviceCapability.PARTY_MODE)

        self.partymode_enabled = result.party_mode_enabled
        self.schedules["active"] = result.active
        self.schedules["time_extension"] = result.time_extension
        self.schedules["party_mode_enabled"] = result.party_mode_enabled
        self.schedules["slots"] = [slot.as_dict() for slot in result.slots]
        self.schedules["one_time_schedule"] = result.one_time_schedule

        if result.one_time_schedule:
            self.capabilities.add(DeviceCapability.ONE_TIME_SCHEDULE)
            self.capabilities.add(DeviceCapability.EDGE_CUT)

    def _determine_updated_at(
        self,
        cfg_payload: dict[str, Any] | None,
        dat_payload: dict[str, Any] | None,
    ) -> datetime:
        """Pick the most accurate timestamp available."""
        if isinstance(cfg_payload, dict) and "dt" in cfg_payload:
            dt_split = cfg_payload["dt"].split("/")
            time_value = cfg_payload.get("tm", "00:00:00")
            try:
                return datetime.fromisoformat(
                    f"{dt_split[2]}-{dt_split[1]}-{dt_split[0]} {time_value}"
                )
            except ValueError:
                pass

        if isinstance(dat_payload, dict) and "tm" in dat_payload:
            tm_value = dat_payload["tm"]
            if isinstance(tm_value, str) and tm_value.endswith("Z"):
                tm_value = f"{tm_value[:-1]}+00:00"
            try:
                return datetime.fromisoformat(tm_value)
            except ValueError:
                pass

        return datetime.now()

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
