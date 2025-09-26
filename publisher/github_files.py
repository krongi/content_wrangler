import base64, requests

def github_commit_files(owner_repo: str, branch: str, token: str, files: dict[str, bytes], message: str):
    """Commit multiple files atomically using Git 'blobs/trees/commits/refs' endpoints."""
    owner, repo = owner_repo.split("/", 1)
    H = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    api = "https://api.github.com"

    # 1) Get current branch HEAD commit & base tree
    ref = requests.get(f"{api}/repos/{owner}/{repo}/git/ref/heads/{branch}", headers=H, timeout=20).json()
    base_commit_sha = ref["object"]["sha"]
    base_commit = requests.get(f"{api}/repos/{owner}/{repo}/git/commits/{base_commit_sha}", headers=H, timeout=20).json()
    base_tree_sha = base_commit["tree"]["sha"]

    # 2) Create blobs for each file
    entries = []
    for path, content in files.items():
        blob = requests.post(
            f"{api}/repos/{owner}/{repo}/git/blobs", headers=H, json={
                "content": base64.b64encode(content).decode("ascii"),
                "encoding": "base64",
            }, timeout=20
        ).json()
        entries.append({"path": path.lstrip("/"), "mode": "100644", "type": "blob", "sha": blob["sha"]})

    # 3) Create a new tree from base + entries
    tree = requests.post(
        f"{api}/repos/{owner}/{repo}/git/trees", headers=H, json={
            "base_tree": base_tree_sha,
            "tree": entries
        }, timeout=20
    ).json()

    # 4) Create commit pointing to the new tree
    commit = requests.post(
        f"{api}/repos/{owner}/{repo}/git/commits", headers=H, json={
            "message": message,
            "tree": tree["sha"],
            "parents": [base_commit_sha],
        }, timeout=20
    ).json()

    # 5) Move branch ref to new commit (no force)
    requests.patch(
        f"{api}/repos/{owner}/{repo}/git/refs/heads/{branch}", headers=H, json={
            "sha": commit["sha"],
            "force": False
        }, timeout=20
    ).raise_for_status()

    return commit
