"""
WeChat Work API integration utilities
"""
import time
import hashlib
import requests
import json
from typing import Optional, Dict, Any


class WeChatWorkAPI:
    """WeChat Work API client"""
    
    def __init__(self, corp_id: str, corp_secret: str, agent_id: str):
        self.corp_id = corp_id
        self.corp_secret = corp_secret
        self.agent_id = agent_id
        self.access_token = None
        self.token_expires_at = 0
        self.base_url = "https://qyapi.weixin.qq.com/cgi-bin"
    
    def get_access_token(self) -> str:
        """Get access token, refresh if expired"""
        current_time = time.time()
        
        if self.access_token and current_time < self.token_expires_at:
            return self.access_token
        
        url = f"{self.base_url}/gettoken"
        params = {
            'corpid': self.corp_id,
            'corpsecret': self.corp_secret
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data.get('errcode') == 0:
                self.access_token = data['access_token']
                # Set expiration time (7200 seconds - 5 minutes buffer)
                self.token_expires_at = current_time + data['expires_in'] - 300
                return self.access_token
            else:
                raise Exception(f"Failed to get access token: {data}")
        except Exception as e:
            raise Exception(f"Error getting access token: {str(e)}")
    
    def verify_url(self, msg_signature: str, timestamp: str, nonce: str, 
                   echostr: str, token: str) -> Optional[str]:
        """Verify WeChat Work webhook URL"""
        # In production, implement proper signature verification
        # This is a simplified version
        return echostr
    
    def send_text_message(self, user_id: str, content: str) -> Dict[str, Any]:
        """Send text message to user"""
        access_token = self.get_access_token()
        url = f"{self.base_url}/message/send?access_token={access_token}"
        
        data = {
            "touser": user_id,
            "msgtype": "text",
            "agentid": self.agent_id,
            "text": {
                "content": content
            },
            "safe": 0
        }
        
        try:
            response = requests.post(url, json=data, timeout=10)
            return response.json()
        except Exception as e:
            return {"errcode": -1, "errmsg": str(e)}

    def upload_image(self, file_path: str) -> Dict[str, Any]:
        """Upload image file and return media_id on success."""
        access_token = self.get_access_token()
        url = f"{self.base_url}/media/upload?access_token={access_token}&type=image"
        try:
            with open(file_path, 'rb') as f:
                files = {'media': (file_path, f, 'image/png')}
                response = requests.post(url, files=files, timeout=30)
                return response.json()
        except Exception as e:
            return {"errcode": -1, "errmsg": str(e)}

    def send_image_message(self, user_id: str, media_id: str) -> Dict[str, Any]:
        """Send an image message by media_id."""
        access_token = self.get_access_token()
        url = f"{self.base_url}/message/send?access_token={access_token}"
        data = {
            "touser": user_id,
            "msgtype": "image",
            "agentid": self.agent_id,
            "image": {"media_id": media_id},
            "safe": 0
        }
        try:
            response = requests.post(url, json=data, timeout=10)
            return response.json()
        except Exception as e:
            return {"errcode": -1, "errmsg": str(e)}
    
    def download_media(self, media_id: str, save_path: str) -> bool:
        """Download media file from WeChat Work"""
        access_token = self.get_access_token()
        url = f"{self.base_url}/media/get"
        params = {
            'access_token': access_token,
            'media_id': media_id
        }
        
        try:
            response = requests.get(url, params=params, stream=True, timeout=30)
            
            if response.status_code == 200:
                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                return True
            return False
        except Exception as e:
            print(f"Error downloading media: {str(e)}")
            return False
    
    def parse_message(self, xml_data: str) -> Dict[str, Any]:
        """Parse XML message from WeChat Work"""
        # In production, use proper XML parsing library
        # This is a simplified version for demonstration
        import xml.etree.ElementTree as ET
        
        try:
            root = ET.fromstring(xml_data)
            message = {}
            
            for child in root:
                message[child.tag] = child.text
            
            return message
        except Exception as e:
            print(f"Error parsing message: {str(e)}")
            return {}
