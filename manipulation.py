import requests, re, dotenv, feedparser, hashlib
from pathlib import Path
from db import was_processed
from readability import Document
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader

dotenv.load_dotenv()

TEMPLATES = Path(__file__).resolve().parent / "templates"
print(str(TEMPLATES))

def clean_text(txt: str) -> str:
    return re.sub(r"\s+", " ", txt).strip()

def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()

def extract_article(url: str, timeout=20) -> str:
    r = requests.get(url, timeout=timeout, headers={"User-Agent":"Mozilla/5.0"})
    r.raise_for_status()
    doc = Document(r.text)
    html = doc.summary(html_partial=True)
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script","style","noscript"]):
        tag.decompose()
    return clean_text(soup.get_text(" ", strip=True))

def token_trim(s: str, max_chars: int) -> str:
    s = s.strip()
    return s if len(s) <= max_chars else s[:max_chars-1].rstrip() + "…"

def render_template(name: str, context: dict) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=False,   # markdown, not HTML
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env.get_template(name).render(**context).strip() + "\n"

def _normalize_hashtags(h) -> list[str]:
    if h is None:
        return []
    if isinstance(h, list):
        return [str(x).strip() for x in h if str(x).strip()]
    if isinstance(h, str):
        # split on whitespace or commas
        parts = [p.strip() for p in re.split(r'[\s,]+', h) if p.strip()]
        return [p if p.startswith("#") else f"#{p}" for p in parts]
    if isinstance(h, dict):
        out = []
        for v in h.values():
            if isinstance(v, list):
                out.extend(str(x).strip() for x in v if str(x).strip())
            elif isinstance(v, str):
                out.append(v.strip())
        return [x if x.startswith("#") else f"#{x}" for x in out]
    return []

def normalize_platforms(p) -> dict:
    defaults = {
        "twitter":   {"enabled": True,  "max_len": 260, "add_link": True},
        "facebook":  {"enabled": True,  "add_link": True},
        "instagram": {"enabled": True,  "add_link": False},
        "tiktok":    {"enabled": True,  "script_seconds": 45},
        "doc_text":  {"enabled": True}
    }

    if isinstance(p, dict):
        out = {k: defaults.get(k, {}).copy() for k in defaults}
        for k, v in p.items():
            if isinstance(v, dict):
                out.setdefault(k, {}).update(v)
            elif isinstance(v, bool):
                out.setdefault(k, {}).update({"enabled": v})
        return out

    if isinstance(p, list):
        out = {k: defaults[k].copy() for k in defaults}
        for k in out: out[k]["enabled"] = False
        for name in p:
            n = str(name).strip().lower()
            if n in out: out[n]["enabled"] = True
        return out

    if isinstance(p, str):
        names = [x.strip().lower() for x in p.replace(",", " ").split() if x.strip()]
        return normalize_platforms(names)

    return {k: defaults[k].copy() for k in defaults}

def format_outputs(article, url, hashtags, platforms, tags):
    tags = tags or []
    title = article.get("title", "").strip()
    summary = article.get("summary", "").strip()
    takeaways = article.get("bullets", []) or []
    link = url or ""
    bullets_block = "\n".join([f"• {b}" for b in takeaways[:4]]) if takeaways else "• Key detail 1\n• Key detail 2"

    platforms = normalize_platforms(platforms)

    # Turn bucket names into hash-tags: "AI_Automation" -> "#AI_Automation"
    base_hashtags = _normalize_hashtags(hashtags)
    tag_hashes = [f"#{t}" for t in tags]
    hashtags_str = " ".join(base_hashtags + tag_hashes).strip()

    tw = fb = ig = tt = doc_text = ""


    if platforms["twitter"]["enabled"]:
        tw = load_template("twitter.txt").format(
            headline=token_trim(title, 120),
            take=token_trim(summary, 200),
            hashtags=hashtags_str,
            link=link if platforms["twitter"].get("add_link", True) else ""
        )
        tw = token_trim(tw, platforms["twitter"].get("max_len", 260))

    if platforms["facebook"]["enabled"]:
        bullets_block = "\n".join([f"• {b}" for b in takeaways[:4]]) if takeaways else "• Key detail 1\n• Key detail 2"
        fb = load_template("facebook.txt").format(
            headline=title,
            summary=summary,
            bullets=bullets_block,
            hashtags=hashtags_str,
            link=link if platforms["facebook"].get("add_link", True) else ""
        )

    if platforms["instagram"]["enabled"]:
        ig = load_template("instagram.txt").format(
            headline=title,
            summary=summary,
            cta="Follow for daily tech breakdowns ↓",
            hashtags=hashtags_str
        )

    if platforms["tiktok"]["enabled"]:
        seconds = int(platforms["tiktok"].get("script_seconds", 45))
        tt = load_template("tiktok.txt").format(
            seconds=seconds,
            hook=f"{title} in {seconds} seconds:",
            body=summary,
            cta="Like & follow for more. Full article in bio."
        )
    
    if platforms["doc_text"]["enabled"]:
        doc_text = load_template("doc.txt").format(
            headline=title,
            summary=summary,
            bullets=bullets_block,
            hashtags=hashtags_str,
            link=link
        )

    return {"twitter": tw.strip(), "facebook": fb.strip(), "instagram": ig.strip(), "tiktok": tt.strip(), "doc_text": doc_text.strip()}

def load_template(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")

def pick_fresh_entries(cfg, con):
    """Return a list of (title, link) for fresh items not yet processed."""
    items = []
    feeds = cfg.get("feeds", [])
    ua = {"User-Agent": "SubvertecTechEngine/1.0 (+https://subvertec.com)"}

    print(f">> Fetching {len(feeds)} feeds with 10s timeout…", flush=True)
    for i, feed_url in enumerate(feeds, 1):
        try:
            print(f"   [{i}/{len(feeds)}] GET {feed_url}", flush=True)
            r = requests.get(feed_url, headers=ua, timeout=10)
            r.raise_for_status()
            parsed = feedparser.parse(r.text)

            count = 0
            for e in parsed.entries[:10]:
                title = (e.get("title") or "").strip()
                link = (e.get("link") or "").strip()
                if not link or not title:
                    continue
                uid = sha1(link)
                if not was_processed(con, uid):
                    items.append((title, link))
                    count += 1
            print(f"      ok: {count} new candidate(s) from this feed", flush=True)

        except requests.exceptions.Timeout:
            print(f"      timeout: {feed_url} (skipping)", flush=True)
        except requests.exceptions.SSLError as se:
            print(f"      SSL error: {feed_url} -> {se} (skipping)", flush=True)
        except requests.exceptions.RequestException as rexc:
            print(f"      HTTP error: {feed_url} -> {rexc} (skipping)", flush=True)
        except Exception as ex:
            print(f"      parse error: {feed_url} -> {ex} (skipping)", flush=True)

    # Dedup by link
    seen, dedup = set(), []
    for t, l in items:
        if l in seen:
            continue
        seen.add(l)
        dedup.append((t, l))

    print(f">> Total candidate articles found: {len(dedup)}", flush=True)
    return dedup

def auto_tags(text: str, buckets: dict[str, list[str]], max_tags: int = 3) -> list[str]:
    """Return up to max_tags bucket names whose keywords appear in text."""
    if not buckets:
        return []
    s = text.lower()
    hits = []
    for tag, kws in buckets.items():
        for kw in kws:
            if kw.lower() in s:
                hits.append(tag)
                break  # one hit per bucket is enough
    # deterministic order; cap to max_tags
    return hits[:max_tags]
