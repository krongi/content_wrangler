import math, os, requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

IMAGE_GENERATION_URL = os.getenv("IMAGE_GENERATION_URL")
API_KEY = os.getenv("XAI_API_KEY")

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]

def _font(size: int):
    for p in _FONT_CANDIDATES:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except: pass
    return ImageFont.load_default()

def cover_grok_watermark(img: Image.Image, text="Subvertec", frac=0.08) -> Image.Image:
    w, h = img.size
    bar_h = max(60, min(int(h * frac), 140))
    y0 = h - bar_h
    d = ImageDraw.Draw(img)
    d.rectangle((0, y0, w, h), fill=(0, 0, 0))
    f = _font(max(24, int(bar_h * 0.45)))
    d.text((18, y0 + (bar_h - f.size)//2), text, fill=(255, 255, 255), font=f)
    return img

def fetch_cover_grok(url: str) -> Image.Image:
    r = requests.get(url, timeout=60); r.raise_for_status()
    img = Image.open(BytesIO(r.content)).convert("RGB")
    return cover_grok_watermark(img)

def llm_image(url: str = IMAGE_GENERATION_URL, api_key: str = API_KEY, model: str = "grok-2-image", prompt: str = "") -> Image.Image:
    headers = {"accept": "application/json", "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "response_format": "url", "prompt": prompt}
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return fetch_cover_grok(data["data"][0]["url"])

def _fit_text(draw, text, font, max_width):
    words, lines, cur = text.split(), [], []
    for w in words:
        test = " ".join(cur + [w])
        if draw.textbbox((0,0), test, font=font)[2] <= max_width or not cur:
            cur.append(w)
        else:
            lines.append(" ".join(cur)); cur = [w]
    if cur: lines.append(" ".join(cur))
    return lines

def generate_hero_image(title: str, summary: str, img_Image: Image.Image, tags=None, size=(1600, 900), brand="Subvertec") -> bytes:
    img = img_Image
    w, h = img.size
    d = ImageDraw.Draw(img)

    # Title
    lines = []
    for fs in range(72, 38, -2):
        f = _font(fs)
        lines = _fit_text(d, title, f, int(w*0.70))
        if len(lines) <= 4: break
    f_title = _font(max(38, min(72, fs)))
    x = int(w*0.10); y = int(h*0.20); gap = int(f_title.size * 0.28)
    for i, line in enumerate(lines):
        d.text((x, y + i*(f_title.size + gap)), line, fill=(240, 240, 255), font=f_title)

    # Subtitle
    sub = " ".join(summary.split()[:22])
    f_sub = _font(30)
    sub_lines = _fit_text(d, sub, f_sub, int(w*0.70))
    y2 = y + len(lines)*(f_title.size + gap) + int(f_title.size*0.8)
    for i, line in enumerate(sub_lines[:3]):
        d.text((x, y2 + i*(f_sub.size + 6)), line, fill=(220, 220, 230), font=f_sub)

    # Export
    buf = BytesIO()
    img.save(buf, format="WEBP", quality=92, method=6)
    return buf.getvalue()
