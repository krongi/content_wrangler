import re, string, difflib

_BULLET_RE = re.compile(r'^(?:-\s+|\*\s+|\u2022\s+|\d{1,2}\.\s+)(.+)$', re.M)

def extract_bullets(text: str) -> list[str]:
    out = []
    for m in _BULLET_RE.finditer(text):
        b = m.group(1).strip()
        b = " ".join(b.split()[:14]).rstrip(",.;:")
        out.append(b)
    return out

def _norm(s: str) -> str:
    s = re.sub(r"\s+", " ", s.lower().translate(str.maketrans("", "", string.punctuation))).strip()
    return s

def dedupe_bullets(summary: str, bullets: list[str], max_count: int = 5, sim: float = 0.82) -> list[str]:
    sents = [_norm(x) for x in re.split(r'(?<=[.!?])\s+', summary) if x.strip()]
    keep, seen = [], []
    for b in bullets:
        nb = _norm(b)
        if any(nb in s or s in nb or difflib.SequenceMatcher(None, nb, s).ratio() >= sim for s in sents):
            continue
        if any(difflib.SequenceMatcher(None, nb, x).ratio() >= sim for x in seen):
            continue
        keep.append(b); seen.append(nb)
        if len(keep) >= max_count: break
    return keep

def fallback_bullets_from_summary(summary: str, want: int = 3) -> list[str]:
    out = []
    for s in [s.strip() for s in re.split(r'(?<=[.!?])\s+', summary) if s.strip()]:
        s = re.sub(r'^[A-Z][a-z]+ (said|reports?|announced) that\s+', '', s)
        out.append(" ".join(s.split()[:14]).rstrip(",.;:"))
        if len(out) >= want: break
    return out
