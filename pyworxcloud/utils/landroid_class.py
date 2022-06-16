"""A class set that helps representing data as wanted."""


class LDict(dict):
    """A Landroid custom dict."""

    def __init__(self, default=None):
        """Init dict."""
        super().__init__(self)
        self.default = default

    # def __delitem__(self, key):
    #     if not isinstance(key, (type(None), list)):
    #         value = super().pop(key)
    #         super().pop(value, None)

    # def __getitem__(self, key):
    #     try:
    #         return super().__getitem__(self, key)
    #     except KeyError:
    #         return self.default

    # def __setitem__(self, key, value):
    #     if key in super():
    #         del super()[key]
    #     super().__setitem__(key, value)

    # def update(self, items):
    #     if isinstance(items, dict):
    #         items = items.items()
    #     for key, value in items:
    #         super()[key] = value
