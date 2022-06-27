"""Defines actions for the devices."""
from __future__ import annotations
import json


from ..exceptions import NoOneTimeScheduleError, NoPartymodeError, OfflineError
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