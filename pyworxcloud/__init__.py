import asyncio
import concurrent.futures
import contextlib
import time

from .worxlandroidapi import *

__version__ = '1.2.19'

StateDict = {
    0: "Idle",
    1: "Home",
    2: "Start sequence",
    3: "Leaving home",
    4: "Follow wire",
    5: "Searching home",
    6: "Searching wire",
    7: "Mowing",
    8: "Lifted",
    9: "Trapped",
    10: "Blade blocked",
    11: "Debug",
    12: "Remote control",
    30: "Going home",
    31: "Zoning",
    32: "Cutting edge",
    33: "Searching area",
    34: "Pause"
}

ErrorDict = {
    0: "No error",
    1: "Trapped",
    2: "Lifted",
    3: "Wire missing",
    4: "Outside wire",
    5: "Rain delay",
    6: "Close door to mow",
    7: "Close door to go home",
    8: "Blade motor blocked",
    9: "Wheel motor blocked",
    10: "Trapped timeout",
    11: "Upside down",
    12: "Battery low",
    13: "Reverse wire",
    14: "Charge error",
    15: "Timeout finding home",
    16: "Locked",
    17: "Battery temperature error"
}

UNKNOWN_ERROR = "Unknown error (%s)"



class WorxCloud:
    """Worx by Landroid Cloud connector."""
    wait = True

    def __init__(self):
        self._worx_mqtt_client_id = ''
        self._worx_mqtt_endpoint = ''

        self._api = WorxLandroidAPI()
        

    async def initialize(self, username, password):
        loop = asyncio.get_running_loop()

        auth = await loop.run_in_executor(None, self._authenticate, username, password)
        if auth is False:
            self._auth_result = False
            return None

        self._auth_result = True
        return True

    def connect(self, dev_id, verify_ssl = True):
        import paho.mqtt.client as mqtt
        self._dev_id = dev_id
        self._get_mac_address()

        self._mqtt = mqtt.Client(self._worx_mqtt_client_id, protocol=mqtt.MQTTv311)

        self._mqtt.on_message = self._forward_on_message
        self._mqtt.on_connect = self._on_connect

        with self._get_cert() as cert:
            self._mqtt.tls_set(certfile=cert)

        if not verify_ssl:
            self._mqtt.tls_insecure_set(True)

        conn_res = self._mqtt.connect(self._worx_mqtt_endpoint, port=8883, keepalive=600)
        if (conn_res):
            #self._auth_result = False
            return None

        self._mqtt.loop_start()
        mqp = self._mqtt.publish(self.mqtt_in, '{}', qos=0, retain=False)
        while not mqp.is_published:
            time.sleep(0.1)

        return True


    @property
    def auth_result(self):
        return self._auth_result

    def _authenticate(self, username, password):
        auth_data = self._api.auth(username, password)

        try:
            self._api.set_token(auth_data['access_token'])
            self._api.set_token_type(auth_data['token_type'])

            self._api.get_profile()
            profile = self._api.data
            self._worx_mqtt_endpoint = profile['mqtt_endpoint']

            self._worx_mqtt_client_id = 'android-' + self._api.uuid
        except:
            return False

    @contextlib.contextmanager
    def _get_cert(self):
        import base64

        certresp = self._api.get_cert()
        cert = base64.b64decode(certresp['pkcs12'])

        with pfx_to_pem(certresp['pkcs12']) as pem_cert:
            yield pem_cert

    def _get_mac_address(self):
        self._fetch()
        self.mqtt_out = self.mqtt_topics['command_out']
        self.mqtt_in = self.mqtt_topics['command_in']
        self.mac = self.mac_address

    def _forward_on_message(self, client, userdata, message):
        import json

        json_message = message.payload.decode('utf-8')
        self._decodeData(json_message)

    def getStatus(self):
        status = self._api.get_status(self.serial_number)
        status = str(status).replace("'","\"")

        self._decodeData(status)

    def _decodeData(self, indata):
        import json

        data = json.loads(indata)
        self.rssi = data['dat']['rsi']
        self.status = data['dat']['ls']
        self.status_description = StateDict[data['dat']['ls']]
        self.error = data['dat']['le']
        self.error_description = ErrorDict[data['dat']['le']]
        self.current_zone = data['dat']['lz']
        self.locked = data['dat']['lk']
        self.battery_temperature = data['dat']['bt']['t']
        self.battery_voltage = data['dat']['bt']['v']
        self.battery_percent = data['dat']['bt']['p']
        self.battery_charging = data['dat']['bt']['c']
        self.battery_charge_cycle = data['dat']['bt']['nr']
        self.blade_time = data['dat']['st']['b']
        self.distance = data['dat']['st']['d']
        self.work_time = data['dat']['st']['wt']
        self.updated = data["cfg"]["tm"] + " " + data["cfg"]["dt"]
        self.schedule_mower_active = data['cfg']['sc']['m']
        self.schedule_variation = data['cfg']['sc']['p']
        self.schedule_day_sunday_start = data['cfg']['sc']['d'][0][0]
        self.schedule_day_sunday_duration = data['cfg']['sc']['d'][0][1]
        self.schedule_day_sunday_boundary = data['cfg']['sc']['d'][0][2]
        self.schedule_day_monday_start = data['cfg']['sc']['d'][1][0]
        self.schedule_day_monday_duration = data['cfg']['sc']['d'][1][1]
        self.schedule_day_monday_boundary = data['cfg']['sc']['d'][1][2]
        self.schedule_day_tuesday_start = data['cfg']['sc']['d'][2][0]
        self.schedule_day_tuesday_duration = data['cfg']['sc']['d'][2][1]
        self.schedule_day_tuesday_boundary = data['cfg']['sc']['d'][2][2]
        self.schedule_day_wednesday_start = data['cfg']['sc']['d'][3][0]
        self.schedule_day_wednesday_duration = data['cfg']['sc']['d'][3][1]
        self.schedule_day_wednesday_boundary = data['cfg']['sc']['d'][3][2]
        self.schedule_day_thursday_start = data['cfg']['sc']['d'][4][0]
        self.schedule_day_thursday_duration = data['cfg']['sc']['d'][4][1]
        self.schedule_day_thursday_boundary = data['cfg']['sc']['d'][4][2]
        self.schedule_day_friday_start = data['cfg']['sc']['d'][5][0]
        self.schedule_day_friday_duration = data['cfg']['sc']['d'][5][1]
        self.schedule_day_friday_boundary = data['cfg']['sc']['d'][5][2]
        self.schedule_day_saturday_start = data['cfg']['sc']['d'][6][0]
        self.schedule_day_saturday_duration = data['cfg']['sc']['d'][6][1]
        self.schedule_day_saturday_boundary = data['cfg']['sc']['d'][6][2]
        self.rain_delay = data['cfg']['rd']
        self.pitch = data['dat']['dmp'][0]
        self.roll = data['dat']['dmp'][1]
        self.yaw = data['dat']['dmp'][2]
        self.firmware = data['dat']['fw']
        self.serial = data['cfg']['sn']
        self.gps_latitude = None
        self.gps_longitude = None

        if "modules" in data['dat']:
            if "4G" in data['dat']['modules']:
                self.gps_latitude = data['dat']['modules']['4G']['gps']['coo'][0]
                self.gps_longitude = data['dat']['modules']['4G']['gps']['coo'][1] 

        self.wait = False

    def _on_connect(self, client, userdata, flags, rc):
        client.subscribe(self.mqtt_out)

    def start(self):
        self._mqtt.publish(self.mqtt_in, '{"cmd":1}', qos=0, retain=False)

    def pause(self):
        self._mqtt.publish(self.mqtt_in, '{"cmd":2}', qos=0, retain=False)

    def stop(self):
        self._mqtt.publish(self.mqtt_in, '{"cmd":3}', qos=0, retain=False)

    def setRainDelay(self, rainDelay):
        msg = '{"rd": %s}' % (rainDelay)
        self._mqtt.publish(self.mqtt_in, msg, qos=0, retain=False)

    def _fetch(self):
        self._api.get_products()
        products = self._api.data

        for attr, val in products[self._dev_id].items():
            setattr(self, str(attr), val)

    def update(self):
        self.wait = True

        self._fetch()
        if self.online:
            self._mqtt.publish(self.mqtt_in, '{}', qos=0, retain=False)
            sleep = 0
            while self.wait:
                time.sleep(0.1)

    def enumerate(self):
        self._api.get_products()
        products = self._api.data
        return len(products)

    def sendData(self, data):
        if self.online:
            self._mqtt.publish(self.mqtt_in, data, qos=0, retain=False)

@contextlib.contextmanager
def pfx_to_pem(pfx_data):
    ''' Decrypts the .pfx file to be used with requests.'''
    ''' Based on https://gist.github.com/erikbern/756b1d8df2d1487497d29b90e81f8068 '''
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
