import os, re
from manipulation import extract_article, clean_text, token_trim

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
