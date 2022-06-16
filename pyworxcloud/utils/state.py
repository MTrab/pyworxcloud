"""States handler."""

from enum import IntEnum

from ..states import ERROR_TO_DESCRIPTION, STATE_TO_DESCRIPTION
from .landroid_class import LDict


class StateType(IntEnum):
    """State types."""

    STATUS = 0
    ERROR = 1


class States(LDict):
    """States class handler."""

    def update(self, new_id):
        self["id"] = new_id
        self["description"] = self.__descriptor[self["id"]]

    def __init__(self, statetype: StateType = StateType.STATUS):
        super().__init__()

        self.__descriptor = STATE_TO_DESCRIPTION
        if statetype == StateType.ERROR:
            self.__descriptor = ERROR_TO_DESCRIPTION

        self["id"] = -1
        self["description"] = self.__descriptor[self["id"]]
