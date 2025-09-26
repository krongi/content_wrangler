import requests
def post_to_buffer(access_token: str, profile_ids: list[str], text: str, link: str):
    url = "https://api.bufferapp.com/1/updates/create.json"
    payload = {
        "text": text,
        "profile_ids": profile_ids,
        "shorten": True,
        "now": True,
        "media[link]": link
    }
    r = requests.post(url, data=payload, headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
    r.raise_for_status()
    return r.json()