"""Test file for debugging only."""

import requests


url = "https://id.worx.com/oauth/token"
request_body = {
    "grant_type": "password",
    "client_id": "150da4d2-bb44-433b-9429-3773adc70a2a",
    "scope": "*",
    "username": "ACCOUNT-EMAIL",
    "password": "ACCOUNT-PASSWORD",
}
headers = {
    "Accept": "application/json",
    "Content-Type": "application/x-www-form-urlencoded",
}

req = requests.post(url, request_body, headers=headers)

print(req.json())
