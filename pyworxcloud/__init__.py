import contextlib

from .wordlandroidapi import *

from pprint import pprint


class WorxCloud:
    """Worx by Landroid Cloud connector."""
    def __init__(self, username, password, receive_message):
        import paho.mqtt.client as mqtt

        self._worx_mqtt_client_id = ''
        self._worx_mqtt_endpoint = ''
        self._callback = receive_message

        self._api = WorxLandroidAPI()
        self._authenticate(username, password)
        self._get_mac_address()

        self._mqtt = mqtt.Client(self._worx_mqtt_client_id, protocol=mqtt.MQTTv311)

        self._mqtt.on_message = self._forward_on_message
        self._mqtt.on_connect = self._on_connect
        with self._get_cert() as cert:
            self._mqtt.tls_set(certfile=cert)

        conn_res = self._mqtt.connect(self._worx_mqtt_endpoint, port=8883, keepalive=600)
        if (conn_res):
            return None

        self._mqtt.loop_start()

    def _authenticate(self, username, password):
        auth_data = self._api.auth(username, password)

        self._api.set_token(auth_data['access_token'])
        self._api.set_token_type(auth_data['token_type'])

        profile = self._api.get_profile()
        self._worx_mqtt_endpoint = profile['mqtt_endpoint']

        self._worx_mqtt_client_id = 'android-' + self._api.uuid

    @contextlib.contextmanager
    def _get_cert(self):
        import base64

        certresp = self._api.get_cert()
        cert = base64.b64decode(certresp['pkcs12'])

        with pfx_to_pem(certresp['pkcs12']) as pem_cert:
            yield pem_cert

    def _get_mac_address(self):
        self.update()
        #products = self._api.get_products()
        #idx = 0
        #self._mac_address = products[idx]["mac_address"]
        self._mac_address = self.mac_address
        self._mqtt_out = self._mqtt_topics['command_out']
        self._mqtt_in = self._mqtt_topics['command_in']

    def _forward_on_message(self, client, userdata, message):
        import json

        json_message = message.payload.decode('utf-8')

        try:
            self._callback(json.loads(json_message))
        except:
            pass

    def _on_connect(self, client, userdata, flags, rc):
        client.subscribe(self._mqtt_out)

    def start(self):
        self.mqttc.publish(self._mqtt_in, '{"cmd":1}', qos=0, retain=False)
    
    def pause(self):
        self.mqttc.publish(self._mqtt_in, '{"cmd":2}', qos=0, retain=False)

    def stop(self):
        self.mqttc.publish(self._mqtt_in, '{"cmd":3}', qos=0, retain=False)

    def update(self):
        products = self._api.get_products()

        for attr, val in products[0].items():
            setattr(self, "_" + str(attr), val)

        for attr in dir(self):
            print(attr)

    @property
    def name(self):
        """Return name for device."""
        try:
            return self._name
        except:
            return None

    @property
    def mac_address(self):
        """Return name for device."""
        try:
            return self._mac_address
        except:
            return None

@contextlib.contextmanager
def pfx_to_pem(pfx_data):
    ''' Decrypts the .pfx file to be used with requests.'''
    '''Based on https://gist.github.com/erikbern/756b1d8df2d1487497d29b90e81f8068'''
    import base64
    import OpenSSL.crypto
    import tempfile

    with tempfile.NamedTemporaryFile(suffix='.pem', delete=False) as t_pem:
        f_pem = open(t_pem.name, 'wb')
        p12 = OpenSSL.crypto.load_pkcs12(base64.b64decode(pfx_data), '')
        f_pem.write(OpenSSL.crypto.dump_privatekey(OpenSSL.crypto.FILETYPE_PEM, p12.get_privatekey()))
        f_pem.write(OpenSSL.crypto.dump_certificate(OpenSSL.crypto.FILETYPE_PEM, p12.get_certificate()))
        ca = p12.get_ca_certificates()
        if ca is not None:
            for cert in ca:
                f_pem.write(OpenSSL.crypto.dump_certificate(OpenSSL.crypto.FILETYPE_PEM, cert))
        f_pem.close()
        yield t_pem.name