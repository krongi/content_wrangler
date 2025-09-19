import re, string, difflib

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