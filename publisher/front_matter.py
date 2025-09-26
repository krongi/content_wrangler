# from __future__ import annotations
# import re, yaml
# from datetime import datetime

# def slugify(title: str) -> str:
#     s = title.lower()
#     s = re.sub(r"[^a-z0-9\s-]", "", s)
#     s = re.sub(r"\s+", "-", s).strip("-")
#     return s[:80]

# def _jekyll_dt(dt: datetime | None = None) -> str:
#     dt = (dt or datetime.now().astimezone())
#     return dt.strftime("%Y-%m-%d %H:%M:%S %z")  # Jekyll-friendly

# def build_front_matter_dict(
#     *,
#     title: str,
#     summary: str = "",
#     tags: list[str] | None = None,
#     categories: list[str] | None = None,
#     date: datetime | None = None,
#     permalink: str | None = None,
#     layout: str = "posts",
#     header_image: str | None = None,
#     seo_title: str | None = None,
#     seo_description: str | None = None,
#     excerpt: str | None = None,
# ):
#     tags = [str(t) for t in (tags or [])]
#     categories = [str(c) for c in (categories or [])]
#     dt = date or datetime.now().astimezone()
#     slug = slugify(title)

#     fm = {
#         "layout": layout,
#         "title": str(title),
#         "date": _jekyll_dt(dt),
#         # "excerpt": (excerpt if excerpt is not None else summary)[:240],
#         "excerpt": (excerpt if excerpt is not None else summary).split(".")[0],
#         "seo_title": (seo_title or title),
#         "seo_description": (seo_description or summary)[:155],
#         "categories": categories,
#         "tags": tags,
#         "permalink": permalink or f"/blog/{slug}/",
#     }
#     if header_image:
#         fm["header_image"] = header_image
#     return fm, slug  # <-- exactly two return values

# def front_matter_text(fm_dict: dict) -> str:
#     yaml_txt = yaml.safe_dump(
#         fm_dict, allow_unicode=True, sort_keys=False, default_flow_style=False, width=1000
#     )
#     return f"---\n{yaml_txt}---\n\n"
