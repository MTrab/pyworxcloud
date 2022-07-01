"""Landroid Cloud callback events"""
# pylint: disable=unnecessary-lambda
from __future__ import annotations

from enum import IntEnum
from typing import Any


class LandroidEvent(IntEnum):
    """Enum for Landroid event types."""

    DATA_RECEIVED = 0
    MQTT_CONNECTION = 1
    MQTT_RATELIMIT = 2
    MQTT_PUBLISH = 3


class EventHandler:
    """Event handler for Landroid Cloud."""

    __events: dict[LandroidEvent, Any] = {}

    def __init__(self) -> None:
        """Initialize the event handler object."""

    def set_handler(self, event: LandroidEvent, func: Any) -> None:
        """Set handler for a LandroidEvent"""
        self.__events.update({event: func})

    def del_handler(self, event: LandroidEvent) -> None:
        """Remove a handler for a LandroidEvent."""
        self.__events.pop(event)

    def call(self, event: LandroidEvent, **kwargs) -> bool:
        """Call a handler if it was set."""
        if not event in self.__events:
            # Event was not set
            return

        if LandroidEvent.DATA_RECEIVED == event:
            self.__events[event](name=kwargs["name"], device=kwargs["device"])
            return True
        elif LandroidEvent.MQTT_CONNECTION == event:
            if not "state" in kwargs:
                # Invalid event call, state is required.
                return False
            if not isinstance(kwargs["state"], bool):
                # Invalid event call, state is required to be a boolean.
                return False

            self.__events[event](state=kwargs["state"])
            return True
        elif LandroidEvent.MQTT_RATELIMIT == event:
            if not "message" in kwargs:
                # Invalid event call, message is required
                return False

            if not isinstance(kwargs["message"], str):
                # Invalid event call, message is required to be a string.
                return False

            self.__events[event](message=kwargs["message"])
            return True
        elif LandroidEvent.MQTT_PUBLISH == event:
            if not kwargs in ["message", "qos", "retain", "device", "topic"]:
                # Invalid event call, missing one or more of the required arguments
                return False

            if (
                not isinstance(kwargs["message"], str)
                and not isinstance(kwargs["device"], str)
                and not isinstance(kwargs["topic"], str)
            ):
                # Invalid event call, one or more of the arguments required to be a string but was not.
                return False

            if not isinstance(kwargs["qos"], int):
                # Invalid event call, one or more of the arguments required to be an integer but was not.
                return False
            if not isinstance(kwargs["retain"], False):
                # Invalid event call, one or more of the arguments required to be a bool but was not.
                return False

            self.__events[event](
                message=kwargs["message"],
                qos=kwargs["qos"],
                retain=kwargs["retain"],
                device=kwargs["device"],
                topic=kwargs["topic"],
            )
            return True
        else:
            # Not a valid LandroidEvent
            return False
