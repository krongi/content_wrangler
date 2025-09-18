import os
import requests
from typing import List, Optional

class BufferClient:
    API = "https://api.bufferapp.com/1/updates/create.json"

    def __init__(self, access_token: str, profile_ids: List[str]):
        self.access_token = os.path.expandvars(access_token)
        self.profile_ids = [os.path.expandvars(pid) for pid in profile_ids]

    def post(self, text: str, link: Optional[str] = None, media: Optional[dict] = None, now: bool = True):
        results = []
        for pid in self.profile_ids:
            payload = {
                "access_token": self.access_token,
                "profile_ids[]": pid,
                "text": text.strip(),
                "now": "true" if now else "false",
            }
            if link:
                payload["attachment"] = "link"
                payload["media[link]"] = link
            if media:
                for k, v in media.items():
                    payload[f"media[{k}]"] = v
            r = requests.post(self.API, data=payload, timeout=20)
            try:
                results.append(r.json())
            except Exception:
                results.append({"status_code": r.status_code, "text": r.text})
        return results
