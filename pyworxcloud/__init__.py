import contextlib

class WorxCloud:
    """Worx by Landroid Cloud connector."""
    def __init__(self, username, password, receive_message):
        import paho.mqtt.client as mqtt

        self._worx_mqtt_client_id = ''
        self._worx_mqtt_endpoint = ''
        self._on_message = receive_message