
import os, hashlib, textwrap, datetime, socket, yaml
from pathlib import Path
from dotenv import load_dotenv
from db import init_db, mark_processed
from llm import filter_revenue_aligned, build_prompt, run_llm
from post import post_to_buffer
from manipulation import extract_article, format_outputs, pick_fresh_entries, auto_tags
from bullets import extract_bullets, dedupe_bullets, fallback_bullets_from_summary
from publisher.jekyll_publisher import github_commit_markdown, jekyll_permalink
from publisher.front_matter import build_front_matter_dict, front_matter_text

socket.setdefaulttimeout(10)

load_dotenv()

BASE = Path(__file__).resolve().parent
DATA_FOLDER = BASE / "data"
TEMPLATES = BASE / "templates"
ARTICLE_DOCS = BASE / "article_docs"
PUBLISHER = BASE / "publisher"
for p in (DATA_FOLDER, TEMPLATES, ARTICLE_DOCS):
    Path(p).mkdir(parents=True, exist_ok=True)
(DB_PATH := DATA_FOLDER / "content.db")

print(">> Tech Content Engine starting…", flush=True)
print(">> CWD:", os.getcwd(), flush=True)
print(">> Base:", BASE, "Data:", DATA_FOLDER, "DB:", DB_PATH, flush=True)

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