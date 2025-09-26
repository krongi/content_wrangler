import os, re
from manipulation import extract_article, clean_text, token_trim

def _create_snippet(article: str, char_count: int = 320) -> str:
    out, total = [], 0
    for s in article.split(". "):
        if not s: continue
        need = len(s) + 1
        if total + need > char_count: break
        out.append(s + "."); total += need
    return "".join(out)

def _strip_md_headings(s: str) -> str:
    return re.sub(r'(?m)^\s*#{1,6}\s+', '', s).strip()

def score_text(text: str, inc: list[str], exc: list[str]) -> int:
    s, score = text.lower(), 0
    for w in inc: 
        if w in s: score += 1
    for w in exc:
        if w in s: score -= 2
    return score

def filter_revenue_aligned(candidates: list[tuple[str,str]], cfg: dict) -> list[tuple[str,str]]:
    inc = [w.lower() for w in cfg.get("revenue_filter", {}).get("include_keywords", [])]
    exc = [w.lower() for w in cfg.get("revenue_filter", {}).get("exclude_keywords", [])]
    min_score = int(cfg.get("revenue_filter", {}).get("min_score", 2))
    kept = []
    print(f">> Revenue filter: min_score={min_score}", flush=True)
    for i, (title, link) in enumerate(candidates, 1):
        try:
            snippet = _create_snippet(extract_article(link))
        except Exception as e:
            print(f"   [{i}] fetch fail -> {e} (scoring title only)", flush=True)
            snippet = ""
        score = score_text((title or "") + " " + snippet, inc, exc)
        print(f"   [{i}] score={score} :: {title}", flush=True)
        if score >= min_score: kept.append((title, link, score))
    kept.sort()
    print(f">> Revenue-aligned kept: {len(kept)} / {len(candidates)}", flush=True)
    return kept

def get_image_prompt(brand, voice, ai_rewrite: str = "") -> str:
    return f"""You are {brand}'s creative lead. Take the input rewrite and create a relevant 2–3 sentence image prompt.

Style: {voice.get('style')}
Audience: {voice.get('audience')}

{ai_rewrite}
"""

def build_prompt(brand, voice, article_text, title):
    return f"""You are {brand}'s tech editor. Rewrite the news in your own words (no quotes).

Style: {voice.get('style')}
Audience: {voice.get('audience')}

Output: a single 4–6 sentence paragraph summary. No lists/bullets/headers.

Title: {title}

ARTICLE:
{article_text}
"""

def run_llm(prompt: str, cfg: dict) -> str:
    provider = cfg.get("provider","none")
    if provider == "openai":
        import openai
        client = openai.OpenAI()
        model = cfg["openai"].get("model","gpt-4o-mini")
        max_tokens = cfg["openai"].get("max_tokens", 500)
        resp = client.chat.completions.create(
            model=model, messages=[{"role":"user","content":prompt}],
            temperature=0.7, max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip()
    elif provider == "grok":
        from xai_sdk import Client
        from xai_sdk.chat import user
        model = cfg["grok"].get("model", "grok-3-mini")
        chat = Client(api_key=os.getenv("XAI_API_KEY")).chat.create(model=model)
        chat.append(user(prompt))
        return _strip_md_headings(chat.sample().content)
    elif provider == "ollama":
        import subprocess
        p = subprocess.run(
            ["ollama","run",cfg["ollama"].get("model","llama3.1:8b")],
            input=prompt.encode(), capture_output=True, check=False
        )
        return p.stdout.decode().strip()
    else:
        m = re.search(r"ARTICLE:(.*)", prompt, re.S)
        article = clean_text(m.group(1)) if m else ""
        return token_trim(article, 1000)
