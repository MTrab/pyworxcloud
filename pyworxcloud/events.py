"""Landroid Cloud callback events"""
# pylint: disable=unnecessary-lambda
from __future__ import annotations

from enum import IntEnum
from typing import Any


class LandroidEvent(IntEnum):
    """Enum for Landroid event types."""

    DATA_RECEIVED = 0
    MQTT_CONNECTION = 1


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

    def call(self, event: LandroidEvent, **kwargs) -> None:
        """Call a handler if it was set."""
        if not event in self.__events:
            # Event was not set
            return

        if LandroidEvent.DATA_RECEIVED == event:
            self.__events[event](name=kwargs["name"], device=kwargs["device"])
        elif LandroidEvent.MQTT_CONNECTION == event:
            if not "state" in kwargs:
                # Invalid event call, state is required.
                return
            if not isinstance(kwargs["state"], bool):
                # Invalid event call, state is required to be a boolean.
                return

            self.__events[event](state=kwargs["state"])
