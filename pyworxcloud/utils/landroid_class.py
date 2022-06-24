"""A class set that helps representing data as wanted."""


class LDict(dict):
    """A Landroid custom dict."""

    def __init__(self, default=None):
        """Init dict."""
        super().__init__(self)
