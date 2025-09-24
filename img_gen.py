import math, os, dotenv, requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

dotenv.load_dotenv()

IMAGE_GENERATION_URL = os.getenv("IMAGE_GENERATION_URL")
API_KEY = os.getenv("XAI_API_KEY")

payload = {
  "model": "grok-2-image", 
  "response_format": "url",
  "prompt": "" 
  }

headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def llm_image(url: str = IMAGE_GENERATION_URL, api_key: str = API_KEY, model: str = "grok-2-image",   prompt: str = "") -> str:
    payload["prompt"] = prompt
    resp = requests.request("POST", url = url, headers = headers, json = payload)
    resp_json = resp.json()
    article_image = fetch_cover_grok(resp_json.get("data")[0].get("url"))
    return article_image

# Try a few common font paths; fall back to PIL default
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]
def _load_font(size: int):
    for p in _FONT_CANDIDATES:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except: pass
    return ImageFont.load_default()

def _palette_for_tags(tags):
    tags = [t.lower() for t in (tags or [])]
    if any(t in tags for t in ("security", "ransomware", "cve", "mfa", "breach")):
        return (18, 18, 36), (200, 30, 70)     # dark → red
    if any(t in tags for t in ("ai", "llm", "automation", "ml")):
        return (20, 18, 40), (120, 60, 220)    # dark → purple
    if any(t in tags for t in ("cloud", "azure", "m365", "unifi", "dns", "network")):
        return (10, 24, 36), (0, 160, 200)     # dark → teal
    return (22, 22, 22), (70, 70, 70)          # neutral

def _draw_gradient(w, h, c1, c2):
    img = Image.new("RGB", (w, h), c1)
    top = Image.new("RGB", (w, h), c2)
    # simple radial-ish mask
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    maxr = int(math.hypot(w, h))
    for r in range(0, maxr, max(1, maxr // 200)):
        a = int(255 * (r / maxr))
        md.ellipse((w//2 - r, h//2 - r, w//2 + r, h//2 + r), outline=a, width=max(1, maxr // 200))
    return Image.composite(top, img, mask)

def _fit_text(draw, text, font, max_width, line_height_mult=1.0):
    # Wrap by width using trial lines
    words = text.split()
    lines, cur = [], []
    for w in words:
        test = " ".join(cur + [w])
        bbox = draw.textbbox((0,0), test, font=font)
        if bbox[2] <= max_width or not cur:
            cur.append(w)
        else:
            lines.append(" ".join(cur))
            cur = [w]
    if cur: lines.append(" ".join(cur))
    return lines

def _font(sz):
    for p in _FONT_CANDIDATES:
        try: return ImageFont.truetype(p, sz)
        except: pass
    return ImageFont.load_default()

def cover_grok_watermark(img: Image.Image, text="Subvertec", frac=0.08) -> Image.Image:
    """Draw a branded footer bar over the bottom area."""
    w, h = img.size
    bar_h = max(60, min(int(h * frac), 140))
    y0 = h - bar_h
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, y0, w, h), fill=(0, 0, 0))
    font = _font(max(24, int(bar_h * 0.45)))
    draw.text((18, y0 + (bar_h - font.size)//2), text, fill=(255, 255, 255), font=font)
    return img

def fetch_cover_grok(url: str, **kwargs) -> Image:
    r = requests.get(url, timeout=60); r.raise_for_status()
    img = Image.open(BytesIO(r.content)).convert("RGB")
    img = cover_grok_watermark(img, **kwargs)
    buf = BytesIO(); img.save(buf, "WEBP", quality=92, method=6)
    return img

def brand_tag(draw, brand, w, h):
    brand_font = _load_font(28)
    br_w, br_h = draw.textbbox((0,0), brand, font=brand_font)[2:]
    pad = 20
    bx = w - br_w - pad*2 - 24
    by = h - br_h - pad*2 - 24
    # pill
    draw.rounded_rectangle((bx, by, bx+br_w+pad*2, by+br_h+pad*2), radius=18, fill=(0,0,0, 180))
    draw.text((bx+pad, by+pad), brand, fill=(230, 230, 240), font=brand_font)
    return draw

def generate_hero_image(title: str, summary: str, img_Image: Image, tags=None, size=(1600, 900), brand="Subvertec") -> bytes:
    w, h = img_Image.size
    bg1, bg2 = _palette_for_tags(tags)
    # img = _draw_gradient(w, h, bg1, bg2)
    img = img_Image
    draw = ImageDraw.Draw(img)

    #Title sizing
    title_font_size = 72
    title_font = _load_font(title_font_size)
    # Shrink font until title fits in ~70% width and <= 4 lines
    for fs in range(72, 38, -2):
        title_font = _load_font(fs)
        lines = _fit_text(draw, title, title_font, int(w*0.70))
        if len(lines) <= 4: break

    # Title block
    x = int(w*0.10)
    y = int(h*0.20)
    line_gap = int(title_font.size * 0.28)
    for i, line in enumerate(lines):
        draw.text((x, y + i*(title_font.size + line_gap)), line, fill=(240, 240, 255), font=title_font)

    # Subtitle (shortened summary)
    sub = " ".join(summary.split()[:22])
    sub_font = _load_font(30)
    sub_lines = _fit_text(draw, sub, sub_font, int(w*0.70))
    y2 = y + len(lines)*(title_font.size + line_gap) + int(title_font.size*0.8)
    for i, line in enumerate(sub_lines[:3]):
        draw.text((x, y2 + i*(sub_font.size + 6)), line, fill=(220, 220, 230), font=sub_font)

    # # # Brand tag
    # # brand_font = _load_font(28)
    # # br_w, br_h = draw.textbbox((0,0), brand, font=brand_font)[2:]
    # # pad = 20
    # # bx = w - br_w - pad*2 - 24
    # # by = h - br_h - pad*2 - 24
    # # # pill
    # # draw.rounded_rectangle((bx, by, bx+br_w+pad*2, by+br_h+pad*2), radius=18, fill=(0,0,0, 180))
    # # draw.text((bx+pad, by+pad), brand, fill=(230, 230, 240), font=brand_font)
    # brand_tag(draw, brand, w, h)


    # mask = Image.new("L", (img.width, img.height), 0)
    # md = ImageDraw.Draw(mask)
    # # bright center (we'll invert to get stronger edges)
    # md.rectangle(
    #     (int(w * 0.06), int(h * 0.06), int(w * 0.94), int(h * 0.94)),
    #     fill=255
    # )
    # # soften the mask so darkening is gradual
    # mask = mask.filter(ImageFilter.GaussianBlur(radius=max(w, h) // 12))

    # # invert -> edges ≈ 255 (strong), center ≈ 0 (none)
    # edge_mask = ImageOps.invert(mask)

    # # build a black overlay with per-pixel alpha = edge strength
    # base_rgba = img.convert("RGBA")
    # overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    # overlay.putalpha(edge_mask)

    # # composite: this darkens edges but keeps the base fully opaque
    # comp = Image.alpha_composite(base_rgba, overlay)

    # # export as opaque RGB
    # rgb = comp.convert("RGB")

    # Export to WebP bytes
    buf = BytesIO()
    img.save(buf, format="WEBP", quality=92, method=6)
    return buf.getvalue()
