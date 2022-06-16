"""Base util classes for Landroid Cloud."""


class DictBase(dict):
    """Base class for Landroid util dict."""

    def __repr__(self) -> str:
        return repr(self.__dict__)


class IntBase(int):
    """Base class for Landroid util int."""

    def __repr__(self) -> str:
        return repr(self.__int__)
