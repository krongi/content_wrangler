# publisher/jekyll_publisher.py

from __future__ import annotations
import base64, json, re, datetime
from pathlib import Path
import requests

# If you moved FM to publisher/front_matter.py, we can bridge to it here
from publisher.front_matter import build_front_matter_dict, front_matter_text

def slugify(title: str) -> str:
    s = title.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    return s[:80]

def jekyll_permalink(base_url: str, date: datetime.datetime, slug: str,
                     pattern: str = "/blog/:title/") -> str:
    """Build a permalink that matches your Jekyll pattern."""
    return (
        base_url.rstrip("/")
        # + pattern.replace(":year", date.strftime("%Y"))
        #          .replace(":month", date.strftime("%m"))
        #          .replace(":day", date.strftime("%d"))
                 .replace(":title", slug)
    )

def github_commit_markdown(
    owner_repo: str,
    branch: str,
    repo_token: str,
    path_in_repo: str,
    content: str,
    commit_msg: str,
):
    """
    Create or update a file in the repo using the GitHub Contents API.
    path_in_repo: e.g. '_posts/2025-09-18-my-post.md'
    """
    if not repo_token:
        raise ValueError("GITHUB_TOKEN is missing or empty.")

    url = f"https://api.github.com/repos/{owner_repo}/contents/{path_in_repo}"
    headers = {
        "Authorization": f"Bearer {repo_token}",
        "Accept": "application/vnd.github+json",
    }

    # Check if file exists to include 'sha' on update
    r = requests.get(url, headers=headers, params={"ref": branch}, timeout=20)
    sha = r.json().get("sha") if r.status_code == 200 else None

    payload = {
        "message": commit_msg,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    resp = requests.put(url, headers=headers, data=json.dumps(payload), timeout=20)
    if resp.status_code >= 400:
        raise RuntimeError(
            f"GitHub commit failed ({resp.status_code}): {resp.text}"
        )
    return resp.json()

# ---- Optional helpers so existing imports don’t explode ----

def build_front_matter(meta: dict) -> str:
    """
    Back-compat wrapper so code calling build_front_matter(meta) still works.
    Expects meta dict with at least title, date (datetime), summary, tags.
    """
    fm_dict, _slug = build_front_matter_dict(
        title=meta.get("title", ""),
        summary=meta.get("summary", ""),
        tags=meta.get("tags", []),
        categories=meta.get("tags", []),
        date=meta.get("date"),
    )
    return front_matter_text(fm_dict)

def write_jekyll_post(repo_dir: str, meta: dict, body_md: str) -> Path:
    """
    Minimal local writer; not used by the Contents API path but kept for imports.
    Writes into <repo_dir>/_posts/YYYY-MM-DD-slug.md
    """
    date = meta.get("date") or datetime.datetime.now()
    slug = meta.get("slug") or slugify(meta.get("title", "post"))
    fname = f"{date.strftime('%Y-%m-%d')}-{slug}.md"
    path = Path(repo_dir) / "_posts" / fname
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = build_front_matter(meta)
    path.write_text(fm + (body_md or ""), encoding="utf-8")
    return path
