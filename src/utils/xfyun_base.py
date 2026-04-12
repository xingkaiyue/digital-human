# src/utils/xfyun_base.py
import base64
import hashlib
import hmac
from datetime import datetime
from time import mktime
from urllib.parse import urlencode
from wsgiref.handlers import format_date_time


class XFYunBase:
    def __init__(self, appid: str, api_key: str, api_secret: str):
        self.appid = appid
        self.api_key = api_key
        self.api_secret = api_secret

    def create_ws_url(self, host: str, path: str) -> str:
        """
        创建讯飞 WebSocket 鉴权 URL
        """
        base_url = f"wss://{host}{path}"
        date = format_date_time(mktime(datetime.now().timetuple()))

        signature_origin = (
            f"host: {host}\n"
            f"date: {date}\n"
            f"GET {path} HTTP/1.1"
        )

        signature_sha = hmac.new(
            self.api_secret.encode("utf-8"),
            signature_origin.encode("utf-8"),
            hashlib.sha256
        ).digest()

        signature = base64.b64encode(signature_sha).decode("utf-8")

        authorization_origin = (
            f'api_key="{self.api_key}", '
            f'algorithm="hmac-sha256", '
            f'headers="host date request-line", '
            f'signature="{signature}"'
        )

        authorization = base64.b64encode(
            authorization_origin.encode("utf-8")
        ).decode("utf-8")

        params = {
            "authorization": authorization,
            "date": date,
            "host": host
        }

        return base_url + "?" + urlencode(params)