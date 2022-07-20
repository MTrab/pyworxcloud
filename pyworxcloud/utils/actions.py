"""Defines actions for the devices."""
from __future__ import annotations

import json

from ..exceptions import (
    NoOneTimeScheduleError,
    NoPartymodeError,
    OfflineError,
    RequestException,
)
from ..helpers import get_logger
from .capability import DeviceCapability
from .mqtt import Command

_LOGGER = get_logger("mqtt")


class Actions:
    """Class for actions."""

    def home(self) -> None:
        """Stop the current task and go home.
        If the knifes was turned on when this is called, it will return home with knifes still turned on.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        if self.online:
            logger = _LOGGER.getChild("command")
            logger.debug("Sending HOME command to %s", self.name)
            self.mqtt.command(self.name, Command.HOME)
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def zonetraining(self) -> None:
        """Start the zone training task.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        if self.online:
            logger = _LOGGER.getChild("command")
            logger.debug("Sending ZONETRAINING command to %s", self.name)
            self.mqtt.command(self.name, Command.ZONETRAINING)
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
                logger = _LOGGER.getChild("command")
                logger.debug("Sending LOCK command to %s", self.name)
                self.mqtt.command(self.name, Command.LOCK)
            else:
                logger = _LOGGER.getChild("command")
                logger.debug("Sending UNLOCK command to %s", self.name)
                self.mqtt.command(self.name, Command.UNLOCK)
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def restart(self):
        """Reboot the device baseboard.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        if self.online:
            logger = _LOGGER.getChild("command")
            logger.debug("Sending RESTART command to %s", self.name)
            self.mqtt.command(self.name, Command.RESTART)
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def safehome(self):
        """Stop and go home with the blades off

        Raises:
            OfflineError: Raised if the device is offline.
        """
        if self.online:
            logger = _LOGGER.getChild("command")
            logger.debug("Sending SAFEHOME command to %s", self.name)
            self.mqtt.command(self.name, Command.SAFEHOME)
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def raindelay(self, rain_delay: str) -> None:
        """Set new rain delay.

        Args:
            rain_delay (str | int): Rain delay in minutes.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        if self.online:
            if not isinstance(rain_delay, str):
                rain_delay = str(rain_delay)
            msg = {"rd": rain_delay}
            self.mqtt.send(self.name, str(msg))
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
                msg = {"sc": {"m": 1}}
            else:
                msg = {"sc": {"m": 0}}

            self.mqtt.send(self.name, str(msg))
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
                msg = {"sc": {"m": 2, "distm": 0}}
            else:
                msg = {"sc": {"m": 1, "distm": 0}}

            self.mqtt.send(self.name, str(msg))
        elif not self.capabilities.check(DeviceCapability.PARTY_MODE):
            raise NoPartymodeError("This device does not support Partymode")
        elif not self.online:
            raise OfflineError("The device is currently offline, no action was sent.")

    def ots(self, boundary: bool, runtime: str) -> None:
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

            msg = {"sc": {"ots": {"bc": int(boundary), "wtm": runtime}}}
            self.mqtt.send(self.name, str(msg))
        elif not self.capabilities.check(DeviceCapability.ONE_TIME_SCHEDULE):
            raise NoOneTimeScheduleError(
                "This device does not support Edgecut-on-demand"
            )
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def setzone(self, zone: str | int, debug: bool = False) -> None:
        """Set zone to be mowed when next mowing task is started.

        Args:
            zone (str | int): Zone to mow, valid possibilities are a number from 1 to 4.

        Raises:
            OfflineError: Raised if the device is offline.
        """
        if self.online:
            if not isinstance(zone, int):
                zone = int(zone)

            if self.zone["starting_point"][zone] == 0:
                raise RequestException("Cannot request this zone as it is not defined.")

            current = self.zone["indicies"]
            new_zones = current

            next_index = self.zone["index"] + 1 if self.zone["index"] < 9 else 0
            while not new_zones[self.zone["index"]] == zone:
                tmp = []
                for i in range(1, 10):
                    tmp.append(new_zones[i])
                tmp.append(new_zones[0])
                new_zones = tmp

            if not debug:
                msg = {"mzv": new_zones}
                self.mqtt.send(self.name, str(msg))
            else:
                return current, new_zones, self.zone["index"], next_index
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def start(self) -> None:
        """Start mowing task

        Raises:
            OfflineError: Raised if the device is offline.
        """
        if self.online:
            logger = _LOGGER.getChild("command")
            logger.debug("Sending START command to %s", self.name)
            self.mqtt.command(self.name, Command.START)
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def pause(self) -> None:
        """Pause the mowing task

        Raises:
            OfflineError: Raised if the device is offline.
        """
        if self.online:
            logger = _LOGGER.getChild("command")
            logger.debug("Sending PAUSE command to %s", self.name)
            self.mqtt.command(self.name, Command.PAUSE)
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def send(self, data: str) -> None:
        """Send raw JSON data to the device.

        Args:
            data (str): Data to be sent, formatted as a valid JSON object.

        Raises:
            OfflineError: Raised if the device isn't online.
        """
        if self.online:
            logger = _LOGGER.getChild("raw_data_publish")
            logger.debug("Sending %s to %s", data, self.name)
            self.mqtt.send(self.name, data)
        else:
            raise OfflineError("The device is currently offline, no action was sent.")

    def refresh(self) -> None:
        """Try to force a refresh of data from the API."""
        if self.online:
            logger = _LOGGER.getChild("forced_refresh")
            logger.debug("Forcing a data refresh from the API for %s", self.name)
            self.mqtt.send(self.name)
        else:
            raise OfflineError("The device is currently offline, no action was sent.")
