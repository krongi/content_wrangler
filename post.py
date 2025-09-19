import subprocess, os

def post_to_buffer(access_token: str, profile_ids: list[str], text: str, link: str):
    import requests, json
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

def git_commit_push(repo_dir: str, ssh_key_path: str, rel_path: str, message: str = "Publish"):
    env = os.environ.copy()
    env["GIT_SSH_COMMAND"] = f"ssh -i {ssh_key_path} -o IdentitiesOnly=yes"
    subprocess.run(["git","-C",repo_dir,"pull","--ff-only"], check=True, env=env)
    subprocess.run(["git","-C",repo_dir,"add",rel_path], check=True, env=env)
    subprocess.run(["git","-C",repo_dir,"commit","-m",message], check=True, env=env)
    subprocess.run(["git","-C",repo_dir,"push"], check=True, env=env)
