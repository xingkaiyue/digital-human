# src/utils/xfyun_auth.py

import base64
import hashlib
import hmac
from datetime import datetime
from time import mktime
from urllib.parse import urlencode
from wsgiref.handlers import format_date_time


def create_ws_url(api_key, api_secret):
    host = "iat-api.xfyun.cn"
    path = "/v2/iat"
    url = f"wss://{host}{path}"

    now = datetime.now()
    date = format_date_time(mktime(now.timetuple()))

    signature_origin = (
        f"host: {host}\n"
        f"date: {date}\n"
        f"GET {path} HTTP/1.1"
    )

    signature_sha = hmac.new(
        api_secret.encode("utf-8"),
        signature_origin.encode("utf-8"),
        digestmod=hashlib.sha256
    ).digest()

    signature = base64.b64encode(signature_sha).decode()

    authorization_origin = (
        f'api_key="{api_key}", '
        f'algorithm="hmac-sha256", '
        f'headers="host date request-line", '
        f'signature="{signature}"'
    )

    authorization = base64.b64encode(
        authorization_origin.encode("utf-8")
    ).decode()

    params = {
        "authorization": authorization,
        "date": date,
        "host": host
    }

    return url + "?" + urlencode(params)