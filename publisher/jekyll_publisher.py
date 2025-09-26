from __future__ import annotations
from io import BytesIO
import base64, json, re, datetime, yaml, requests

def slugify(title: str) -> str:
    s = title.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    return s[:80]

def jekyll_permalink(base_url: str, date: datetime.datetime, slug: str,
                     pattern: str = "/blog/:title/") -> str:
    return base_url.rstrip("/").replace(":title", slug)

def github_commit_markdown(
    owner_repo: str,
    branch: str,
    repo_token: str,
    path_in_repo: str,
    content: str,
    commit_msg: str,
):
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

def build_front_matter(meta: dict) -> str:
    
    fm_dict, _slug = build_front_matter_dict(
        title=meta.get("title", ""),
        summary=meta.get("summary", ""),
        tags=meta.get("tags", []),
        categories=meta.get("tags", []),
        date=meta.get("date"),
    )
    return front_matter_text(fm_dict)

def _jekyll_dt(dt: datetime.datetime | None = None) -> str:
    dt = (dt or datetime.now().astimezone())
    return dt.strftime("%Y-%m-%d %H:%M:%S %z")  # Jekyll-friendly

def build_front_matter_dict(
    *,
    title: str,
    summary: str = "",
    tags: list[str] | None = None,
    categories: list[str] | None = None,
    date: datetime.datetime | None = None,
    permalink: str | None = None,
    layout: str = "posts",
    header_image: str | None = None,
    seo_title: str | None = None,
    seo_description: str | None = None,
    excerpt: str | None = None,
):
    tags = [str(t) for t in (tags or [])]
    categories = [str(c) for c in (categories or [])]
    dt = date or datetime.now().astimezone()
    slug = slugify(title)

    fm = {
        "layout": layout,
        "title": str(title),
        "date": _jekyll_dt(dt),
        # "excerpt": (excerpt if excerpt is not None else summary)[:240],
        "excerpt": (excerpt if excerpt is not None else summary).split(".")[0],
        "seo_title": (seo_title or title),
        "seo_description": (seo_description or summary)[:155],
        "categories": categories,
        "tags": tags,
        "permalink": permalink or f"/blog/{slug}/",
    }
    if header_image:
        fm["header_image"] = header_image
    return fm, slug  # <-- exactly two return values

def front_matter_text(fm_dict: dict) -> str:
    yaml_txt = yaml.safe_dump(
        fm_dict, allow_unicode=True, sort_keys=False, default_flow_style=False, width=1000
    )
    return b"---\n" + yaml_txt.encode('utf-8') + b"---\n\n"