# publisher/github_files.py
import base64, requests

def github_commit_file(owner_repo: str, branch: str, token: str,
                       path: str, content_bytes: bytes, message: str):
    """
    Create or update a file via the 'contents' API.
    - owner_repo: 'owner/repo'
    - branch: target branch name (must exist)
    - path: repo-relative path WITHOUT a leading slash
    """
    path = path.lstrip("/")  # API expects no leading slash
    base = f"https://api.github.com/repos/{owner_repo}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # 1) Check if file exists on this branch to fetch its sha
    sha = None
    g = requests.get(base, headers=headers, params={"ref": branch}, timeout=20)
    if g.status_code == 200:
        try:
            sha = g.json().get("sha")
        except Exception:
            sha = None
    elif g.status_code not in (404, 422):
        # Unexpected GET error – surface details
        raise RuntimeError(f"GitHub GET {g.status_code} for {path} on {branch}: {g.text}")

    # 2) PUT create/update
    payload = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode("ascii"),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(base, headers=headers, json=payload, timeout=20)
    if not r.ok:
        try:
            detail = r.json()
        except Exception:
            detail = r.text
        raise RuntimeError(f"GitHub PUT {r.status_code} for {path} on {branch}: {detail}")
    return r.json()