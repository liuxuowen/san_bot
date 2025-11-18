"""WeChat Service Account API wrapper."""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, Optional

import requests


class WeChatServiceAPI:
    """Minimal client for interacting with a WeChat Service Account."""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        token: str,
        encoding_aes_key: str | None = None,
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.token = token
        self.encoding_aes_key = encoding_aes_key
        self.access_token: Optional[str] = None
        self.token_expires_at = 0.0
        self.base_url = "https://api.weixin.qq.com/cgi-bin"

    def get_access_token(self) -> str:
        now = time.time()
        if self.access_token and now < self.token_expires_at:
            return self.access_token

        url = f"{self.base_url}/token"
        params = {
            "grant_type": "client_credential",
            "appid": self.app_id,
            "secret": self.app_secret,
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if data.get("errcode") and data["errcode"] != 0:
            raise RuntimeError(f"Failed to get access token: {data}")
        self.access_token = data["access_token"]
        self.token_expires_at = now + data.get("expires_in", 7200) - 300
        return self.access_token

    def verify_signature(
        self,
        signature: str,
        timestamp: str,
        nonce: str,
        msg_encrypt: str | None = None,
    ) -> bool:
        """Verify signature for either GET or POST requests."""
        parts = [self.token, timestamp, nonce]
        if msg_encrypt:
            parts.append(msg_encrypt)
        parts.sort()
        raw = "".join(parts)
        calc = hashlib.sha1(raw.encode("utf-8")).hexdigest()
        return calc == signature

    def verify_url(self, signature: str, timestamp: str, nonce: str, echostr: str) -> Optional[str]:
        return echostr if self.verify_signature(signature, timestamp, nonce) else None

    @staticmethod
    def parse_message(xml_data: str) -> Dict[str, Any]:
        import xml.etree.ElementTree as ET

        try:
            root = ET.fromstring(xml_data)
            message: Dict[str, Any] = {}
            for child in root:
                message[child.tag] = child.text
            return message
        except Exception as exc:  # noqa: BLE001
            print(f"Error parsing message: {exc}")
            return {}

    def _post_json(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        headers = {"Content-Type": "application/json; charset=utf-8"}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            response = requests.post(url, data=body, headers=headers, timeout=10)
            return response.json()
        except Exception as exc:  # noqa: BLE001
            return {"errcode": -1, "errmsg": str(exc)}

    def send_text_message(self, user_id: str, content: str) -> Dict[str, Any]:
        token = self.get_access_token()
        url = f"{self.base_url}/message/custom/send?access_token={token}"
        payload = {
            "touser": user_id,
            "msgtype": "text",
            "text": {"content": content},
        }
        return self._post_json(url, payload)

    def upload_image(self, file_path: str) -> Dict[str, Any]:
        token = self.get_access_token()
        url = f"{self.base_url}/media/upload?access_token={token}&type=image"
        try:
            with open(file_path, "rb") as handle:
                files = {"media": (file_path, handle, "image/png")}
                response = requests.post(url, files=files, timeout=30)
                return response.json()
        except Exception as exc:  # noqa: BLE001
            return {"errcode": -1, "errmsg": str(exc)}

    def send_image_message(self, user_id: str, media_id: str) -> Dict[str, Any]:
        token = self.get_access_token()
        url = f"{self.base_url}/message/custom/send?access_token={token}"
        payload = {
            "touser": user_id,
            "msgtype": "image",
            "image": {"media_id": media_id},
        }
        return self._post_json(url, payload)

    def download_media(self, media_id: str, save_path: str) -> tuple[bool, str | None]:
        token = self.get_access_token()
        url = f"{self.base_url}/media/get"
        params = {"access_token": token, "media_id": media_id}
        try:
            response = requests.get(url, params=params, stream=True, timeout=30)
            content_type = response.headers.get("Content-Type", "").lower()
            if "application/json" in content_type or "text/plain" in content_type:
                try:
                    data = response.json()
                except Exception:  # noqa: BLE001
                    data = {"errcode": -1, "errmsg": response.text[:200]}
                return False, str(data)
            if response.status_code == 200:
                with open(save_path, "wb") as handle:
                    for chunk in response.iter_content(chunk_size=8192):
                        handle.write(chunk)
                return True, None
            return False, f"HTTP {response.status_code}"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
