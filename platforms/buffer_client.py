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

def use_buffer(cfg):
    use_buffer = cfg["post"].get("use_buffer", False)
    dry_run = cfg["post"].get("dry_run", True)
    buffer_client = None
    if use_buffer:
        from platforms.buffer_client import BufferClient
        buffer_cfg = cfg["post"]["buffer"]
        buffer_client = BufferClient(buffer_cfg["access_token"], buffer_cfg.get("profile_ids", []))
    return buffer_client