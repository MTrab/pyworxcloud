import asyncio

API_HOST = "api.worxlandroid.com"
API_BASE = ("https://{}/api/v2").format(API_HOST)


class WorxLandroidAPI():
    def __init__(self):
        self._token = self._generate_identify_token('725f542f5d2c4b6a5145722a2a6a5b736e764f6e725b462e4568764d4b58755f6a767b2b76526457')
        self._token_type = 'app'

    def set_token(self, token):
        self._token = token

    def set_token_type(self, token_type):
        self._token_type = token_type

    def _generate_identify_token(self, seed_token):
        text_to_char = [ord(c) for c in API_HOST]

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

    def auth(self, username, password, type='app'):
        import uuid
        import json

        self.uuid = str(uuid.uuid1())


        payload_data = {}
        payload_data['username'] = username
        payload_data['password'] = password
        payload_data['grant_type'] = "password"
        payload_data['client_id'] = 1
        payload_data['type'] = type
        payload_data['client_secret'] = self._token
        payload_data['scope'] = "*"
        #payload_data['uuid'] = self.uuid

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
                req = requests.post(API_BASE + path, data=payload, headers=self._get_headers(), timeout=10)
            else:
                req = requests.get(API_BASE + path, headers=self._get_headers(), timeout=10)

            if not req.ok:
                return False
        except:
            raise("Timeout connecting")
            return False

        return req.json()

    @property
    def data(self):
        return self._data