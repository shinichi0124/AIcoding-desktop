"""G tile + lowercase 'ai' badge. Classic opaque BMP ICO (16/24/32/48).

PNG-compressed ICO frames paint as a white taskbar square on Windows.
Large art is a 256 PNG beside the ICO.

Run:
  C:\\ProgramData\\anaconda3\\python.exe scripts\\make_icon.py
"""
from __future__ import annotations

import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
G_PNG = ROOT / "sources" / "windows" / "app" / "web" / "g-logo.png"
OUT = ROOT / "sources" / "windows" / "app" / "web" / "assets"
OUT.mkdir(parents=True, exist_ok=True)

ICON_NAME = "ai-coding-desktop.ico"
SIZES = [16, 24, 32, 48]
SS = 8

# kimi-moonlit accent tile (matches in-app brand-mark)
BG_TOP = (111, 92, 224)   # accent-strong
BG_BOT = (139, 124, 246)  # accent
# dark chip for the 'ai' overlay — distinguishes from other G programs
BADGE_BG = (13, 17, 32)
BADGE_FG = (232, 234, 246)
BADGE_EDGE = (255, 255, 255)


def _gradient(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        t = y / max(1, size - 1)
        r = round(BG_TOP[0] + (BG_BOT[0] - BG_TOP[0]) * t)
        g = round(BG_TOP[1] + (BG_BOT[1] - BG_TOP[1]) * t)
        b = round(BG_TOP[2] + (BG_BOT[2] - BG_TOP[2]) * t)
        for x in range(size):
            px[x, y] = (r, g, b)
    return img


def _white_g() -> Image.Image:
    src = Image.open(G_PNG).convert("RGBA")
    _r, _g, _b, a = src.split()
    white = Image.new("L", src.size, 255)
    return Image.merge("RGBA", (white, white, white, a))


def _font(px: int) -> ImageFont.ImageFont:
    fonts = Path(r"C:\Windows\Fonts")
    for name in ("segoeuib.ttf", "seguisb.ttf", "segoeui.ttf", "calibrib.ttf", "arialbd.ttf"):
        p = fonts / name
        if p.is_file():
            try:
                return ImageFont.truetype(str(p), px)
            except OSError:
                continue
    return ImageFont.load_default()


def render(size: int) -> Image.Image:
    """Fully opaque square. Badge is lowercase 'ai' (AI coding mark)."""
    S = size * SS
    img = _gradient(S)
    g = _white_g()
    gw = int(S * 0.78)
    g = g.resize((gw, gw), Image.Resampling.LANCZOS)
    gx = int(S * 0.04)
    gy = int(S * 0.02)
    img = img.convert("RGBA")
    img.alpha_composite(g, (gx, gy))

    # Compact corner chip so the G stays readable at 16/32px.
    bs = int(S * (0.38 if size >= 32 else 0.34))
    badge = Image.new("RGBA", (bs, bs), (0, 0, 0, 0))
    d = ImageDraw.Draw(badge)
    rad = int(bs * 0.22)
    edge = max(SS, bs // 12)
    d.rounded_rectangle([0, 0, bs - 1, bs - 1], radius=rad, fill=BADGE_BG + (255,), outline=BADGE_EDGE + (255,), width=edge)
    if size >= 24:
        font = _font(int(bs * 0.52))
        d.text((bs / 2, bs / 2 + bs * 0.02), "ai", font=font, fill=BADGE_FG + (255,), anchor="mm")
    pad = max(0, int(S * 0.03))
    img.alpha_composite(badge, (S - bs - pad, S - bs - pad))

    img = img.resize((size, size), Image.Resampling.LANCZOS).convert("RGBA")
    # flatten onto the tile color so ICO stays fully opaque
    flat = Image.new("RGBA", (size, size), BG_BOT + (255,))
    flat.alpha_composite(img)
    return flat


def _dib_xor_and(im: Image.Image) -> bytes:
    w, h = im.size
    pixels = im.load()
    xor_rows = []
    for y in range(h - 1, -1, -1):
        row = bytearray()
        for x in range(w):
            r, g, b, _a = pixels[x, y]
            row += bytes((b, g, r, 255))
        xor_rows.append(bytes(row))
    xor = b"".join(xor_rows)
    row_bytes = ((w + 31) // 32) * 4
    and_mask = bytes(row_bytes * h)
    header = struct.pack(
        "<IiiHHIIiiII",
        40, w, h * 2, 1, 32, 0, len(xor), 0, 0, 0, 0,
    )
    return header + xor + and_mask


def write_ico_classic(path: Path, images: list[Image.Image]) -> None:
    count = len(images)
    header = struct.pack("<HHH", 0, 1, count)
    entries = []
    payloads = []
    offset = 6 + 16 * count
    for im in images:
        w, h = im.size
        data = _dib_xor_and(im)
        bw = 0 if w >= 256 else w
        bh = 0 if h >= 256 else h
        entries.append(struct.pack("<BBBBHHII", bw, bh, 0, 0, 1, 32, len(data), offset))
        payloads.append(data)
        offset += len(data)
    path.write_bytes(header + b"".join(entries) + b"".join(payloads))


def _assert_classic_bmp(path: Path) -> None:
    raw = path.read_bytes()
    count = struct.unpack_from("<H", raw, 4)[0]
    for i in range(count):
        o = 6 + i * 16
        off = struct.unpack_from("<I", raw, o + 12)[0]
        if raw[off : off + 4] == b"\x89PNG":
            raise SystemExit(f"FATAL: PNG frame in {path} index {i}")
        bi = struct.unpack_from("<I", raw, off)[0]
        if bi != 40:
            raise SystemExit(f"FATAL: non-DIB frame in {path} index {i} biSize={bi}")
    print(f"OK classic BMP ICO: {path.name} frames={count} bytes={path.stat().st_size}")


def main() -> None:
    if not G_PNG.is_file():
        raise SystemExit(f"missing {G_PNG}")
    images = [render(s) for s in SIZES]
    ico = OUT / ICON_NAME
    png = OUT / "ai-coding-desktop.png"
    preview = ROOT / "icon-preview.png"
    write_ico_classic(ico, images)
    render(256).save(png)
    render(256).save(preview)
    _assert_classic_bmp(ico)
    sample = render(32)
    assert sample.getpixel((0, 0))[3] == 255
    print(f"wrote {ico}")
    print(f"wrote {png}")
    print(f"wrote {preview}")


if __name__ == "__main__":
    main()
