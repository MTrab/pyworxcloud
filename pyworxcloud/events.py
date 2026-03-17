"""Landroid Cloud callback events"""

# pylint: disable=unnecessary-lambda
from __future__ import annotations

import asyncio
import inspect
import logging
from enum import IntEnum
from typing import Any


class LandroidEvent(IntEnum):
    """Enum for Landroid event types."""

    DATA_RECEIVED = 0
    MQTT_CONNECTION = 1
    MQTT_RATELIMIT = 2
    MQTT_PUBLISH = 3
    LOG = 4
    API = 5


_LOGGER = logging.getLogger("pyworxcloud.events")


def check_syntax(args: dict[str, Any], objs: list[str], expected_type: Any) -> bool:
    """Check if the object is of the expected type."""
    for obj in objs:
        if obj not in args:
            _LOGGER.debug("%s was not found in %s", obj, args)
            return False
        if not isinstance(args[obj], expected_type):
            _LOGGER.debug(
                "%s was of type %s and not as expected %s",
                obj,
                type(obj),
                expected_type,
            )
            return False

    return True


class EventHandler:
    """Event handler for Landroid Cloud."""

    def __init__(self) -> None:
        """Initialize the event handler object."""
        self.__events: dict[LandroidEvent, Any] = {}

    def set_handler(self, event: LandroidEvent, func: Any) -> None:
        """Set handler for a LandroidEvent"""
        self.__events.update({event: func})

    @staticmethod
    def _invoke(handler: Any, **kwargs) -> None:
        """Invoke sync or async event handlers safely."""
        signature = inspect.signature(handler)
        parameters = signature.parameters.values()
        accepts_var_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters
        )

        if accepts_var_kwargs:
            call_kwargs = kwargs
        else:
            accepted_names = {
                parameter.name
                for parameter in signature.parameters.values()
                if parameter.kind
                in (
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.KEYWORD_ONLY,
                )
            }
            call_kwargs = {
                key: value for key, value in kwargs.items() if key in accepted_names
            }

        result = handler(**call_kwargs)
        if not inspect.isawaitable(result):
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(result)
            return

        loop.create_task(result)

    def del_handler(self, event: LandroidEvent) -> None:
        """Remove a handler for a LandroidEvent."""
        self.__events.pop(event, None)

    def call(self, event: LandroidEvent, **kwargs) -> bool:
        """Call a handler if it was set."""
        if event not in self.__events:
            # Event was not set
            return False

        if LandroidEvent.DATA_RECEIVED == event:
            from .utils.devices import DeviceHandler

            if not check_syntax(kwargs, ["name"], str) or not check_syntax(
                kwargs, ["device"], DeviceHandler
            ):
                _LOGGER.warning(
                    "requirements for attributes was not fulfilled, not sending event!"
                )
                return False

            self._invoke(
                self.__events[event], name=kwargs["name"], device=kwargs["device"]
            )
            return True
        elif LandroidEvent.API == event:
            from .utils.devices import DeviceHandler

            api_payload = kwargs.get("api_data")
            has_valid_api_payload = False
            if "api_data" in kwargs:
                if not isinstance(api_payload, dict):
                    _LOGGER.debug(
                        "api_data was of type %s and not as expected %s",
                        type(api_payload),
                        dict,
                    )
                    return False
                has_valid_api_payload = True

            has_valid_name_device = check_syntax(
                kwargs, ["name"], str
            ) and check_syntax(kwargs, ["device"], DeviceHandler)

            if has_valid_name_device and not has_valid_api_payload:
                api_payload = {"name": kwargs["name"], "device": kwargs["device"]}
                has_valid_api_payload = True

            if has_valid_api_payload:
                invoke_kwargs = {"api_data": api_payload}
                if has_valid_name_device:
                    invoke_kwargs["name"] = kwargs["name"]
                    invoke_kwargs["device"] = kwargs["device"]
                self._invoke(self.__events[event], **invoke_kwargs)
                return True

            _LOGGER.warning(
                "requirements for API event attributes were not fulfilled, not sending event!"
            )
            return False
        elif LandroidEvent.MQTT_CONNECTION == event:
            if not check_syntax(kwargs, ["state"], bool):
                return False

            self._invoke(self.__events[event], state=kwargs["state"])
            return True
        elif LandroidEvent.MQTT_RATELIMIT == event:
            if not check_syntax(kwargs, ["message"], str):
                return False

            self._invoke(self.__events[event], message=kwargs["message"])
            return True
        elif LandroidEvent.MQTT_PUBLISH == event:
            if not check_syntax(kwargs, ["message", "device", "topic"], str):
                return False

            if not check_syntax(kwargs, ["qos"], int):
                return False

            if not check_syntax(kwargs, ["retain"], bool):
                return False

            self._invoke(
                self.__events[event],
                message=kwargs["message"],
                qos=kwargs["qos"],
                retain=kwargs["retain"],
                device=kwargs["device"],
                topic=kwargs["topic"],
            )
            return True
        elif LandroidEvent.LOG == event:
            if not check_syntax(kwargs, ["message", "level"], str):
                return False

            self._invoke(
                self.__events[event],
                message=kwargs["message"],
                level=kwargs["level"],
            )
            return True
        else:
            # Not a valid LandroidEvent
            return False
