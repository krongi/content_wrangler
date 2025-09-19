
import os, time, re, sqlite3, hashlib, textwrap, datetime, feedparser, requests, socket, yaml, subprocess, difflib, string
from bs4 import BeautifulSoup
from readability import Document
from pathlib import Path
from dotenv import load_dotenv
from publisher.jekyll_publisher import github_commit_markdown, jekyll_permalink
from publisher.front_matter import build_front_matter_dict, front_matter_text


socket.setdefaulttimeout(10)

load_dotenv()

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
TEMPLATES = BASE / "templates"
ARTICLE_DOCS = BASE / "article_docs"
for p in (DATA, TEMPLATES, ARTICLE_DOCS):
    Path(p).mkdir(parents=True, exist_ok=True)
(DB_PATH := DATA / "content.db")

print(">> Tech Content Engine starting…", flush=True)
print(">> CWD:", os.getcwd(), flush=True)
print(">> Base:", BASE, "Data:", DATA, "DB:", DB_PATH, flush=True)

_BULLET_RE = re.compile(r'^(?:-\s+|\*\s+|\u2022\s+|\d{1,2}\.\s+)(.+)$', re.M)

def extract_bullets(text: str) -> list[str]:
    # Grab lines that start with -, *, •, or "1. "
    bullets = [m.group(1).strip() for m in _BULLET_RE.finditer(text)]
    # Trim long bullets
    out = []
    for b in bullets:
        words = b.split()
        if len(words) > 14:
            b = " ".join(words[:14]).rstrip(",.;:")  # keep them punchy
        out.append(b)
    return out

def _norm(s: str) -> str:
    s = s.lower()
    s = s.translate(str.maketrans("", "", string.punctuation))
    s = re.sub(r"\s+", " ", s).strip()
    return s

def dedupe_bullets(summary: str, bullets: list[str], max_count: int = 5, sim: float = 0.82) -> list[str]:
    # Remove bullets that basically repeat any summary sentence or each other
    sents = re.split(r'(?<=[.!?])\s+', summary)
    sents = [_norm(x) for x in sents if x.strip()]
    keep, seen = [], []
    for b in bullets:
        nb = _norm(b)
        # too similar to any summary sentence?
        if any(nb in s or s in nb or difflib.SequenceMatcher(None, nb, s).ratio() >= sim for s in sents):
            continue
        # too similar to an already kept bullet?
        if any(difflib.SequenceMatcher(None, nb, x).ratio() >= sim for x in seen):
            continue
        keep.append(b)
        seen.append(nb)
        if len(keep) >= max_count:
            break
    return keep

def fallback_bullets_from_summary(summary: str, want: int = 3) -> list[str]:
    # If model didn’t give bullets, synthesize short ones from distinct sentences
    sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', summary) if s.strip()]
    out = []
    for s in sents:
        # Make it short & action/impact oriented
        s = re.sub(r'^[A-Z][a-z]+ (said|reports?|announced) that\s+', '', s)
        words = s.split()
        out.append(" ".join(words[:14]).rstrip(",.;:"))
        if len(out) >= want:
            break
    return out

def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()

def init_db():
    sqlite3
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS processed (
        id TEXT PRIMARY KEY,
        url TEXT,
        title TEXT,
        created_at INTEGER
    )
    """)
    con.commit()
    return con

def was_processed(con, uid: str) -> bool:
    cur = con.cursor()
    cur.execute("SELECT 1 FROM processed WHERE id=?", (uid,))
    return cur.fetchone() is not None

def mark_processed(con, uid: str, url: str, title: str):
    cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO processed (id, url, title, created_at) VALUES (?, ?, ?, ?)",
                (uid, url, title, int(time.time())))
    con.commit()

def clean_text(txt: str) -> str:
    return re.sub(r"\s+", " ", txt).strip()

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

def run_llm(prompt: str, cfg: dict) -> str:
    provider = cfg.get("provider","none")
    if provider == "openai":
        import openai  # pip install openai>=1.0
        client = openai.OpenAI()
        model = cfg["openai"].get("model","gpt-4o-mini")
        max_tokens = cfg["openai"].get("max_tokens", 500)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role":"user","content":prompt}],
            temperature=0.7,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip()
    elif provider == "grok":
        from xai_sdk import Client
        from xai_sdk.chat import user, system
        model = cfg["grok"].get("model", "grok-3-mini")
        client = Client(api_key=os.getenv("XAI_API_KEY"))
        chat = client.chat.create(model=model)
        chat.append(user(prompt))
        resp = chat.sample()
        print(resp.content)
        return resp.content
    elif provider == "ollama":
        import subprocess
        p = subprocess.run(["ollama","run",cfg["ollama"].get("model","llama3.1:8b")],
                           input=prompt.encode("utf-8"),
                           capture_output=True, check=False)
        return p.stdout.decode("utf-8").strip()
    else:
        # extractive fallback
        m = re.search(r"ARTICLE:(.*)", prompt, re.S)
        article = clean_text(m.group(1)) if m else ""
        return token_trim(article, 1000)

def load_template(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")

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

def build_prompt(brand, voice, article_text, title):
    return f"""You are {brand}'s tech editor. Rewrite the news in your own words (no quotes, no verbatim).

Style: {voice.get('style')}
Audience: {voice.get('audience')}

Output EXACTLY this format:
1) A tight 4–6 sentence summary (context + why it matters for SMBs/MSPs).
2) A line that says: "Takeaways:"
3) 3–5 bullets, each ≤ 14 words, starting with "- ". No sentences copied from the summary.
   Focus bullets on implications, risks, costs, or actions for SMBs/MSPs.

Title: {title}

ARTICLE:
{article_text}
"""

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

def score_text(text: str, inc: list[str], exc: list[str]) -> int:
    """Simple keyword scoring."""
    s = text.lower()
    score = 0
    for w in inc:
        if w in s:
            score += 1
    for w in exc:
        if w in s:
            score -= 2
    return score

def llm_is_revenue_aligned(title: str, snippet: str, cfg: dict) -> bool:
    """Optional: second-pass gate using your LLM (very cheap prompt)."""
    try:
        if cfg.get("llm", {}).get("provider") != "openai":
            return True  # if no LLM, accept keyword result
        import openai
        client = openai.OpenAI()
        prompt = (
            "You are a marketing filter for an MSP/AI consulting firm. "
            "Answer strictly 'yes' or 'no'. Keep 'yes' only if this article could lead to paid services "
            "(Microsoft 365/Azure, security/ransomware/CVE/MFA, DNS/network/UniFi, automation/AI/chatbots, "
            "cloud/Proxmox/Docker/K8s, backup/DR, SMB compliance).\n\n"
            f"Title: {title}\nSnippet: {snippet}\n"
        )
        resp = client.chat.completions.create(
            model=cfg["llm"].get("openai", {}).get("model", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=2,
        )
        ans = (resp.choices[0].message.content or "").strip().lower()
        return ans.startswith("y")
    except Exception:
        # fail open to avoid blocking the pipeline on LLM hiccups
        return True

def filter_revenue_aligned(candidates: list[tuple[str,str]], cfg: dict) -> list[tuple[str,str]]:
    """
    From (title, link) pairs, keep only articles relevant for lead-gen/services.
    Uses keyword scoring over title+extracted snippet; optional LLM second pass.
    """
    inc = [w.lower() for w in cfg.get("revenue_filter", {}).get("include_keywords", [])]
    exc = [w.lower() for w in cfg.get("revenue_filter", {}).get("exclude_keywords", [])]
    min_score = int(cfg.get("revenue_filter", {}).get("min_score", 2))
    use_llm = bool(cfg.get("revenue_filter", {}).get("use_llm_second_pass", False))

    kept = []
    print(f">> Revenue filter: min_score={min_score}, use_llm={use_llm}", flush=True)

    for i, (title, link) in enumerate(candidates, 1):
        try:
            # quick content fetch for better signal (shorten to avoid long prompts)
            art = extract_article(link)
            snippet = art[:1200]
        except Exception as e:
            print(f"   [{i}] fetch fail -> {e} (scoring title only)", flush=True)
            snippet = ""

        base = (title or "") + " " + snippet
        score = score_text(base, inc, exc)
        print(f"   [{i}] score={score} :: {title}", flush=True)

        if score < min_score:
            continue

        if use_llm:
            if not llm_is_revenue_aligned(title, snippet, cfg):
                print(f"      LLM gate: NO", flush=True)
                continue
            print(f"      LLM gate: YES", flush=True)

        kept.append((title, link))

    print(f">> Revenue-aligned kept: {len(kept)} / {len(candidates)}", flush=True)
    return kept

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

def main():
    print(">> Loading config.yaml …", flush=True)
    cfg = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))
    print(f">> Feeds: {len(cfg.get('feeds', []))}, provider: {cfg.get('llm',{}).get('provider')}", flush=True)

    con = init_db()
    print(">> DB initialized", flush=True)

    # candidates = pick_fresh_entries(cfg, con)
    # print(f">> Candidate articles found: {len(candidates)}", flush=True)

    candidates = pick_fresh_entries(cfg, con)
    print(f">> Candidate articles found: {len(candidates)}", flush=True)

    # 🔎 keep only revenue-relevant stories
    candidates = filter_revenue_aligned(candidates, cfg)
    if not candidates:
        print(">> No revenue-aligned candidates. Try lowering min_score or adding keywords.", flush=True)
        return

    if not candidates:
        print("No fresh items found."); return

    to_process = candidates[: cfg.get("articles_per_run", 1)]
    print(f"Processing {len(to_process)} article(s).")

    use_buffer = cfg["post"].get("use_buffer", False)
    dry_run = cfg["post"].get("dry_run", True)
    buffer_client = None
    if use_buffer:
        from platforms.buffer_client import BufferClient
        buffer_cfg = cfg["post"]["buffer"]
        buffer_client = BufferClient(buffer_cfg["access_token"], buffer_cfg.get("profile_ids", []))

    for title, link in to_process:
        print(f"\n=== {title} ===\n{link}")
        try:
            art_text = extract_article(link)
        except Exception as e:
            print(f"Failed to fetch article: {e}")
            continue

        prompt = build_prompt(cfg["brand_name"], cfg["voice"], art_text, title)
        rewritten = run_llm(prompt, cfg.get("llm", {"provider":"none"}))

       # summary + bullets
        summary = " ".join([s.strip() for s in rewritten.split("\n")[0:6] if s.strip()])

        bullets = extract_bullets(rewritten)
        if not bullets:
            bullets = fallback_bullets_from_summary(summary, want=4)

        bullets = dedupe_bullets(summary, bullets, max_count=5, sim=0.82)
        if not bullets:  # absolute fallback so we never ship empty bullets
            bullets = fallback_bullets_from_summary(summary, want=3)

        buckets = cfg.get("tag_buckets", {})
        tags = auto_tags(title + " " + summary, buckets)
        print(f">> Auto-tags: {tags}", flush=True)

        article_pack = {"title": title, "summary": summary, "bullets": bullets, "tags": tags}
        out = format_outputs(article_pack, link, cfg.get("hashtags", []), cfg.get("platforms", {}), tags)

        repo_owner_repo = os.getenv("GITHUB_PAGES_REPO", "subv3rsiv3/website")  # e.g., "Subvertec/subvertec.github.io"
        repo_branch     = os.getenv("GITHUB_PAGES_BRANCH", "main")          # or "main"
        repo_token      = os.getenv("GITHUB_TOKEN")                           # classic token with repo scope or a fine-grained token
        site_base_url   = os.getenv("SITE_BASE_URL", "https://subvertec.com") # your domain

        now  = datetime.datetime.now()
        # Build safe, Jekyll-friendly front matter
        fm_dict, slug = build_front_matter_dict(
            title=title,
            summary=article_pack.get("summary",""),
            tags=article_pack.get("tags", []),
            categories=article_pack.get("tags", []),
            date=now,  # keeps filename date and FM date in sync
        )

        # Body (dedented so you don’t get weird leading spaces)
        body_md = textwrap.dedent(f"""{article_pack['summary']}

        **Key takeaways**
        {os.linesep.join([f"- {b}" for b in article_pack['bullets'][:5]])}

        **Source:** [{link}]({link})
        """).strip() + "\n"

        content = front_matter_text(fm_dict) + body_md

        fname = f"_posts/{now.strftime('%Y-%m-%d')}-{slug}.md"
        github_commit_markdown(
            repo_owner_repo, repo_branch, repo_token, fname, content, f"Publish: {title}"
        )

        permalink = jekyll_permalink(
            site_base_url, now, slug, os.getenv("JEKYLL_PERMALINK", "/:year/:month/:day/:title/")
        )
        print(">> Published:", permalink)

        if os.getenv("BUFFER_ACCESS_TOKEN") and os.getenv("BUFFER_PROFILE_1"):
            buf_profiles = [os.getenv("BUFFER_PROFILE_1")]
            fb_text = out["facebook"] or (out["twitter"] or article_pack["summary"])
            print(">> Posting to Buffer…")
            print(post_to_buffer(os.getenv("BUFFER_ACCESS_TOKEN"), buf_profiles, fb_text, permalink))


        print("\n--- Twitter Draft ---\n", out["twitter"])
        print("\n--- Facebook Draft ---\n", out["facebook"])
        print("\n--- Instagram Draft ---\n", out["instagram"])
        print("\n--- TikTok Script ---\n", out["tiktok"])
        print("\n--- doc_text Draft ---\n", out["doc_text"])

        if use_buffer and not dry_run and buffer_client:
            result = buffer_client.post(text=out["facebook"] or out["twitter"], link=link)
            print("Buffer result:", result)
        
        with open(f"{ARTICLE_DOCS}/{title}.doc_text", "w") as doc_text:
            doc_text.write(out["doc_text"])

        mark_processed(con, hashlib.sha1(link.encode("utf-8")).hexdigest(), link, title)

if __name__ == "__main__":
    main()