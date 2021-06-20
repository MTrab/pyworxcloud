import asyncio

API_BASE = "https://{}/api/v2"

clouds = {
    "worx": {
        "url": 'api.worxlandroid.com',
        "key": '725f542f5d2c4b6a5145722a2a6a5b736e764f6e725b462e4568764d4b58755f6a767b2b76526457'
    },
    "kress": {
        "url": 'api.kress-robotik.com',
        "key": '5a1c6f60645658795b78416f747d7a591a494a5c6a1c4d571d194a6b595f5a7f7d7b5656771e1c5f'
    },
    "landxcape": {
        "url": 'api.landxcape-services.com',
        "key": '071916003330192318141c080b10131a056115181634352016310817031c0b25391c1a176a0a0102'
    }
}



class WorxLandroidAPI():
    def __init__(self):
        self.cloud = clouds["worx"]
        self._token_type = 'app'
        
    def set_token(self, token):
        self._token = token

    def set_token_type(self, token_type):
        self._token_type = token_type

    def _generate_identify_token(self, seed_token):
        text_to_char = [ord(c) for c in self.cloud["url"]]

        import re
        step_one = re.findall(r".{1,2}", seed_token)
        step_two = list(map((lambda hex: int(hex, 16)), step_one))

        import functools
        import operator
        step_three = list(map((lambda foo: functools.reduce((lambda x, y: operator.xor(x, y)), text_to_char, foo)), step_two))
        step_four = list(map(chr, step_three))

        final = ''.join(step_four)
        return final

    def _get_headers(self):
        header_data = {}
        header_data['Content-Type'] = 'application/json'
        header_data['Authorization'] = self._token_type + ' ' + self._token

        return header_data

    def auth(self, username, password, cloud, type='app'):
        import uuid
        import json

        self.uuid = str(uuid.uuid1())
        self.cloud = clouds[cloud]
        self._api_host = (API_BASE).format(self.cloud["url"])

        self._token = self._generate_identify_token(self.cloud["key"])

        payload_data = {}
        payload_data['username'] = username
        payload_data['password'] = password
        payload_data['grant_type'] = "password"
        payload_data['client_id'] = 1
        payload_data['type'] = type
        payload_data['client_secret'] = self._token
        payload_data['scope'] = "*"

        payload = json.dumps(payload_data)

        callData = self._call('/oauth/token', payload)
        
        return callData

    def get_profile(self):
        callData = self._call('/users/me')
        self._data = callData
        return callData

    def get_cert(self):
        callData = self._call('/users/certificate')
        self._data = callData
        return callData

    def get_products(self):
        callData = self._call('/product-items')
        self._data = callData
        return callData

    def get_status(self, serial):
        callStr = "/product-items/{}/status".format(serial)
        callData = self._call(callStr)
        return callData

    def _call(self, path, payload=None):
        import requests

        try:
            if payload:
                req = requests.post(self._api_host + path, data=payload, headers=self._get_headers(), timeout=10)
            else:
                req = requests.get(self._api_host + path, headers=self._get_headers(), timeout=10)


            if not req.ok:
                return False
        except:
            raise("Timeout connecting")
            return False

        return req.json()

    @property
    def data(self):
        return self._data