#!/usr/bin/env python3
"""
Generate Instagram Reels 02–07 (1080x1920, 15.0s, 30 fps, H.264 + AAC) + Cover PNGs
for @evacheecks, adhering strictly to DESIGN-RULES.md:
- ZERO perimeter borders/outlines around cards, panels, pills, chips, avatars, or buttons
- NO headline "biscuit pills" (crisp wide-tracked uppercase plain kickers only)
- Separation exclusively via tonal fill contrast, whitespace, and soft ambient drop shadows
- Generic dark-graphite punch-hole Android mockups only (Entry 13)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import wave
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SHOTS_DIR = Path("/tmp/demo_shots")
DEFAULT_OUT_DIR = Path("/tmp/reels_out")

W, H = 1080, 1920
FPS = 30
DURATION_SEC = 15.0
TOTAL_FRAMES = int(FPS * DURATION_SEC)

FONT_SERIF_BOLD = "/usr/share/fonts/opentype/urw-base35/P052-Bold.otf"
FONT_SERIF_BI = "/usr/share/fonts/opentype/urw-base35/P052-BoldItalic.otf"
FONT_SANS_REG = "/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/Roboto-Regular.ttf"
FONT_SANS_MED = "/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/Roboto-Medium.ttf"
FONT_SANS_BOLD = "/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/Roboto-Bold.ttf"
FONT_COND_BOLD = "/usr/share/fonts/truetype/roboto/unhinted/RobotoCondensed-Bold.ttf"

_FONT_CACHE: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    key = (path, size)
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = ImageFont.truetype(path, size)
    return _FONT_CACHE[key]


def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def ease_in_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        return 4.0 * t * t * t
    return 1.0 - ((-2.0 * t + 2.0) ** 3) / 2.0


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def hex_rgb(value: str) -> Tuple[int, int, int]:
    h = value.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def hex_rgba(value: str, alpha: int = 255) -> Tuple[int, int, int, int]:
    r, g, b = hex_rgb(value)
    return (r, g, b, alpha)


def tracked_text_size(fnt: ImageFont.FreeTypeFont, text: str, tracking: float) -> Tuple[float, float]:
    if not text:
        return 0.0, 0.0
    total_w = 0.0
    max_h = 0.0
    for i, ch in enumerate(text):
        bb = fnt.getbbox(ch)
        cw = (bb[2] - bb[0]) if bb else 0
        adv = fnt.getlength(ch)
        total_w += adv + (tracking if i < len(text) - 1 else 0.0)
        if bb:
            max_h = max(max_h, bb[3] - bb[1])
    return total_w, max_h


def draw_tracked_text(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[float, float],
    text: str,
    fnt: ImageFont.FreeTypeFont,
    fill: Tuple[int, ...],
    tracking: float = 0.0,
    anchor_center_x: bool = False,
) -> None:
    x, y = xy
    if anchor_center_x:
        w, _ = tracked_text_size(fnt, text, tracking)
        x = x - w / 2.0
    cx = x
    for i, ch in enumerate(text):
        draw.text((cx, y), ch, font=fnt, fill=fill)
        cx += fnt.getlength(ch) + (tracking if i < len(text) - 1 else 0.0)


def draw_star_polygon(
    draw: ImageDraw.ImageDraw, cx: float, cy: float, outer_r: float, inner_r: float, fill: Tuple[int, ...]
) -> None:
    pts = []
    for i in range(10):
        ang = -math.pi / 2.0 + i * (math.pi / 5.0)
        r = outer_r if i % 2 == 0 else inner_r
        pts.append((cx + math.cos(ang) * r, cy + math.sin(ang) * r))
    draw.polygon(pts, fill=fill)


def draw_checkmark(draw: ImageDraw.ImageDraw, cx: float, cy: float, size: float, fill: Tuple[int, ...], width: int = 4) -> None:
    p1 = (cx - size * 0.42, cy + size * 0.02)
    p2 = (cx - size * 0.10, cy + size * 0.34)
    p3 = (cx + size * 0.44, cy - size * 0.30)
    draw.line([p1, p2, p3], fill=fill, width=width, joint="curve")


def draw_cross(draw: ImageDraw.ImageDraw, cx: float, cy: float, size: float, fill: Tuple[int, ...], width: int = 4) -> None:
    d = size * 0.34
    draw.line([(cx - d, cy - d), (cx + d, cy + d)], fill=fill, width=width)
    draw.line([(cx - d, cy + d), (cx + d, cy - d)], fill=fill, width=width)


def build_background(bg_center: str, bg_edge: str, grid_tint: Tuple[int, int, int]) -> Image.Image:
    """Create signature deep radial studio gradient + subtle faint 64px architectural grid."""
    yy, xx = np.mgrid[0:H, 0:W]
    dx = (xx - W * 0.5) / (W * 0.68)
    dy = (yy - H * 0.42) / (H * 0.52)
    dist = np.clip(np.sqrt(dx * dx + dy * dy), 0.0, 1.0)
    t = dist ** 1.35

    c0 = np.array(hex_rgb(bg_center), dtype=np.float32)
    c1 = np.array(hex_rgb(bg_edge), dtype=np.float32)
    arr = c0[None, None, :] * (1.0 - t[..., None]) + c1[None, None, :] * t[..., None]

    # Subtle 64px grid lines (+4 brightness on line)
    grid_mask = ((xx % 64 == 0) | (yy % 64 == 0)).astype(np.float32) * 0.045
    gt = np.array(grid_tint, dtype=np.float32)
    arr = np.clip(arr * (1.0 - grid_mask[..., None]) + gt[None, None, :] * grid_mask[..., None], 0, 255)
    return Image.fromarray(arr.astype(np.uint8), "RGB").convert("RGBA")


def make_shadow_box(
    w: int, h: int, radius: int, fill_rgba: Tuple[int, int, int, int], shadow_alpha: int = 95, blur: int = 24, dy: int = 12
) -> Tuple[Image.Image, int]:
    """
    Create a crisp 2x supersampled borderless rounded card with ambient soft shadow.
    Returns (RGBA image including padding margin, margin_px). Zero perimeter outlines!
    """
    pad = blur * 2 + abs(dy) + 8
    cw, ch = w + pad * 2, h + pad * 2

    # Soft shadow mask
    shad = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shad)
    sd.rounded_rectangle([pad, pad + dy, pad + w, pad + h + dy], radius=radius, fill=(0, 0, 0, shadow_alpha))
    shad = shad.filter(ImageFilter.GaussianBlur(blur))

    # 2x supersampled crisp borderless fill
    ss = 2
    card2x = Image.new("RGBA", (cw * ss, ch * ss), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card2x)
    cd.rounded_rectangle(
        [pad * ss, pad * ss, (pad + w) * ss, (pad + h) * ss],
        radius=radius * ss,
        fill=fill_rgba,
    )
    card = card2x.resize((cw, ch), Image.Resampling.LANCZOS)
    return Image.alpha_composite(shad, card), pad


def draw_borderless_pill(
    layer: Image.Image,
    box: Tuple[int, int, int, int],
    radius: int,
    fill_rgba: Tuple[int, int, int, int],
    shadow: bool = False,
) -> None:
    """Draw a 2x-antialiased borderless rounded pill directly onto an RGBA canvas. NEVER uses outline."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return
    pad = 28 if shadow else 4
    ss = 2
    tmp = Image.new("RGBA", ((w + pad * 2) * ss, (h + pad * 2) * ss), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    td.rounded_rectangle([pad * ss, pad * ss, (pad + w) * ss, (pad + h) * ss], radius=radius * ss, fill=fill_rgba)
    sm = tmp.resize((w + pad * 2, h + pad * 2), Image.Resampling.LANCZOS)
    if shadow:
        sh = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sh)
        sd.rounded_rectangle([pad, pad + 8, pad + w, pad + h + 8], radius=radius, fill=(0, 0, 0, 72))
        sh = sh.filter(ImageFilter.GaussianBlur(12))
        sm = Image.alpha_composite(sh, sm)
    layer.alpha_composite(sm, (x0 - pad, y0 - pad))


def draw_kicker(
    layer: Image.Image,
    y: int,
    text: str,
    accent_rgb: Tuple[int, int, int],
    show_dot: bool = True,
    font_size: int = 23,
    tracking: float = 3.2,
) -> None:
    """
    Boss rule #2: NO headline 'biscuit pills'.
    Renders clean wide-tracked uppercase plain typography with a small accent square/dot (no pill border/box).
    """
    d = ImageDraw.Draw(layer)
    f = font(FONT_COND_BOLD, font_size)
    tw, th = tracked_text_size(f, text, tracking)
    dot_gap = 20 if show_dot else 0
    total_w = tw + dot_gap
    sx = (W - total_w) / 2.0
    if show_dot:
        dot_y = y + th * 0.45
        r = 5
        d.ellipse([sx - r + 4, dot_y - r, sx + r + 4, dot_y + r], fill=(*accent_rgb, 255))
        sx += dot_gap
    draw_tracked_text(d, (sx, y), text, f, (*accent_rgb, 245), tracking=tracking)


def draw_mixed_serif_headline(
    draw: ImageDraw.ImageDraw,
    y_start: int,
    lines: List[List[Tuple[str, bool]]],
    size: int = 62,
    line_gap: int = 12,
    accent_rgb: Tuple[int, int, int] = (50, 212, 165),
    white_rgb: Tuple[int, int, int] = (244, 246, 244),
) -> int:
    """
    Draw centered two- or three-line serif headline mixing P052-Bold + P052-BoldItalic accent spans.
    Returns final y below text block.
    """
    f_reg = font(FONT_SERIF_BOLD, size)
    f_it = font(FONT_SERIF_BI, size)
    cy = y_start
    for segs in lines:
        total_w = 0.0
        parts = []
        for txt, is_em in segs:
            f = f_it if is_em else f_reg
            w = f.getlength(txt)
            parts.append((txt, f, is_em, w))
            total_w += w
        cx = (W - total_w) / 2.0
        for txt, f, is_em, w in parts:
            col = (*accent_rgb, 255) if is_em else (*white_rgb, 255)
            draw.text((cx, cy), txt, font=f, fill=col)
            cx += w
        cy += size + line_gap
    return cy


def build_phone_shell(screen_w: int, screen_h: int) -> Tuple[Image.Image, Tuple[int, int, int, int], Image.Image]:
    """
    Build a crisp generic dark-graphite punch-hole Android mockup shell + rounded screen mask (Entry 13).
    Zero iPhone notch or Dynamic Island. Returns (shadow+bezel RGBA layer, (sx, sy, sw, sh), screen_alpha_mask).
    """
    bezel = max(10, int(round(screen_w * 0.032)))
    top_chin = bezel
    bot_chin = bezel
    body_w = screen_w + bezel * 2
    body_h = screen_h + top_chin + bot_chin
    outer_r = int(round(body_w * 0.088))
    inner_r = max(18, outer_r - bezel)
    margin = 44

    cw, ch = body_w + margin * 2, body_h + margin * 2
    # Soft deep drop shadow behind phone
    shad = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shad)
    sd.rounded_rectangle(
        [margin, margin + 18, margin + body_w, margin + body_h + 18],
        radius=outer_r,
        fill=(0, 0, 0, 145),
    )
    shad = shad.filter(ImageFilter.GaussianBlur(22))

    # 2x supersampled metallic hardware shell + hardware side buttons
    ss = 2
    shell2x = Image.new("RGBA", (cw * ss, ch * ss), (0, 0, 0, 0))
    shd = ImageDraw.Draw(shell2x)
    bx0, by0 = margin * ss, margin * ss
    bx1, by1 = (margin + body_w) * ss, (margin + body_h) * ss
    # Volume & power side rockers (right side, graphite metallic)
    btn_x0 = bx1 - 2
    btn_x1 = bx1 + int(bezel * 0.36 * ss)
    shd.rounded_rectangle([btn_x0, by0 + int(body_h * 0.22 * ss), btn_x1, by0 + int(body_h * 0.34 * ss)], radius=3, fill=(48, 53, 58, 255))
    shd.rounded_rectangle([btn_x0, by0 + int(body_h * 0.38 * ss), btn_x1, by0 + int(body_h * 0.45 * ss)], radius=3, fill=(48, 53, 58, 255))

    # Outer graphite rim & subtle matte bezel
    shd.rounded_rectangle([bx0, by0, bx1, by1], radius=outer_r * ss, fill=(38, 42, 46, 255))
    shd.rounded_rectangle([bx0 + 3, by0 + 3, bx1 - 3, by1 - 3], radius=outer_r * ss - 2, fill=(21, 24, 27, 255))

    # Transparent cutout for screen? We'll composite screen inside (sx, sy, sw, sh) with inner_mask cleanly, then draw status bar on top!
    shell = shell2x.resize((cw, ch), Image.Resampling.LANCZOS)
    base = Image.alpha_composite(shad, shell)

    sx = margin + bezel
    sy = margin + top_chin

    # Rounded screen mask
    mask2x = Image.new("L", (screen_w * ss, screen_h * ss), 0)
    md = ImageDraw.Draw(mask2x)
    md.rounded_rectangle([0, 0, screen_w * ss - 1, screen_h * ss - 1], radius=inner_r * ss, fill=255)
    mask = mask2x.resize((screen_w, screen_h), Image.Resampling.LANCZOS)

    return base, (sx, sy, screen_w, screen_h), mask


def build_status_bar(screen_w: int, dark_bg: bool) -> Image.Image:
    """
    Android punch-hole status bar strip (height scaled to screen_w).
    Keeps web page header cleanly below camera punch-hole dot (Entry 13).
    """
    bar_h = max(24, int(round(screen_w * 0.068)))
    ss = 2
    img = Image.new("RGBA", (screen_w * ss, bar_h * ss), (22, 24, 27, 255) if dark_bg else (246, 243, 236, 255))
    d = ImageDraw.Draw(img)
    fg = (232, 232, 230, 255) if dark_bg else (28, 28, 26, 255)
    f = font(FONT_SANS_BOLD, int(bar_h * 0.44 * ss))
    d.text((int(screen_w * 0.065 * ss), int(bar_h * 0.27 * ss)), "9:41", font=f, fill=fg)

    # Center punch-hole camera dot
    cx = (screen_w * ss) // 2
    cy = (bar_h * ss) // 2
    cam_r = max(7, int(bar_h * 0.25 * ss))
    d.ellipse([cx - cam_r - 2, cy - cam_r - 2, cx + cam_r + 2, cy + cam_r + 2], fill=(42, 46, 50, 255))
    d.ellipse([cx - cam_r, cy - cam_r, cx + cam_r, cy + cam_r], fill=(10, 12, 14, 255))
    d.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=(28, 42, 54, 255))

    # Signal bars + battery icon (top right)
    rx = int(screen_w * 0.92 * ss)
    # Battery outline & fill
    bw, bh = int(bar_h * 0.68 * ss), int(bar_h * 0.34 * ss)
    by0 = cy - bh // 2
    bx0 = rx - bw
    d.rounded_rectangle([bx0, by0, rx, by0 + bh], radius=3, fill=None, outline=fg, width=2)  # hardware battery icon
    d.rectangle([bx0 + 4, by0 + 4, rx - 6, by0 + bh - 4], fill=fg)
    d.rectangle([rx + 1, cy - bh // 4, rx + 4, cy + bh // 4], fill=fg)

    # Signal steps left of battery
    sbx = bx0 - int(bar_h * 0.52 * ss)
    for idx in range(4):
        sh = int((0.14 + idx * 0.06) * bar_h * ss)
        x_b = sbx + idx * int(bar_h * 0.10 * ss)
        d.rectangle([x_b, cy + bh // 2 - sh, x_b + int(bar_h * 0.06 * ss), cy + bh // 2], fill=fg)

    return img.resize((screen_w, bar_h), Image.Resampling.LANCZOS)


class DemoAsset:
    """Preloads and caches resized demo page strip + sticky bar + phone shell."""

    def __init__(self, slug: str, dark_status: bool, shots_dir: Path, target_sw: int, target_sh: int, meta_entry: dict):
        self.slug = slug
        self.dark_status = dark_status
        self.sw = target_sw
        self.sh = target_sh
        self.meta = meta_entry

        self.shell_img, self.screen_rect, self.screen_mask = build_phone_shell(target_sw, target_sh)
        self.status_bar = build_status_bar(target_sw, dark_status)
        self.status_h = self.status_bar.height
        self.viewport_h = target_sh - self.status_h

        # Pre-resize full-page scroll strip cleanly to target screen_w
        full_src = Image.open(shots_dir / f"{slug}_full.png").convert("RGBA")
        self.css_to_px = float(target_sw) / 390.0
        scaled_h = int(round(full_src.height * (float(target_sw) / float(full_src.width))))
        self.full_strip = full_src.resize((target_sw, scaled_h), Image.Resampling.LANCZOS)
        self.max_scroll = max(0, scaled_h - self.viewport_h)

        # Hero exact viewport (preserves dark scrim/hero look at y=0)
        hero_src = Image.open(shots_dir / f"{slug}_hero.png").convert("RGBA")
        hero_h = int(round(hero_src.height * (float(target_sw) / float(hero_src.width))))
        self.hero_img = hero_src.resize((target_sw, hero_h), Image.Resampling.LANCZOS)

        # Sticky bottom bar if demo has one
        bar_path = shots_dir / f"{slug}_bar.png"
        self.bar_img: Optional[Image.Image] = None
        if bar_path.exists() and meta_entry.get("barHeightCss", 0) > 0:
            bsrc = Image.open(bar_path).convert("RGBA")
            bh = int(round(bsrc.height * (float(target_sw) / float(bsrc.width))))
            self.bar_img = bsrc.resize((target_sw, bh), Image.Resampling.LANCZOS)
        self.hero_bottom_px = int(round(meta_entry.get("heroBottomCss", 650) * self.css_to_px))

    def css_offset(self, selector: str, fallback: int = 0, top_margin_css: int = 16) -> int:
        val = self.meta.get("offsets", {}).get(selector, fallback) - top_margin_css
        return min(self.max_scroll, max(0, int(round(val * self.css_to_px))))

    def render_phone(self, scroll_px: float, alpha_mult: float = 1.0) -> Image.Image:
        """Render complete phone bezel + status bar + scrolled viewport + sticky bottom CTA bar."""
        y = int(round(max(0.0, min(float(self.max_scroll), scroll_px))))
        vp = Image.new("RGBA", (self.sw, self.sh), (245, 242, 236, 255))
        vp.paste(self.status_bar, (0, 0))

        slice_img = self.full_strip.crop((0, y, self.sw, min(self.full_strip.height, y + self.viewport_h)))
        vp.paste(slice_img, (0, self.status_h))

        # Overlay authentic sticky bottom CTA bar when active
        if self.bar_img is not None:
            show_bar = (self.slug == "saffron-and-salt") or (y + self.viewport_h * 0.45 >= self.hero_bottom_px)
            if show_bar:
                vp.alpha_composite(self.bar_img, (0, self.sh - self.bar_img.height))

        phone = self.shell_img.copy()
        sx, sy, sw, sh = self.screen_rect
        clipped = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        clipped.paste(vp, (0, 0), self.screen_mask)
        phone.alpha_composite(clipped, (sx, sy))

        if alpha_mult < 0.999:
            a = phone.split()[3].point(lambda p: int(p * alpha_mult))
            phone.putalpha(a)
        return phone


def paste_centered(canvas: Image.Image, overlay: Image.Image, center_y: int) -> None:
    x = (W - overlay.width) // 2
    y = int(round(center_y - overlay.height / 2.0))
    canvas.alpha_composite(overlay, (x, y))


def apply_alpha(img: Image.Image, alpha: float) -> Image.Image:
    if alpha >= 0.999:
        return img
    if alpha <= 0.001:
        return Image.new("RGBA", img.size, (0, 0, 0, 0))
    out = img.copy()
    a = out.split()[3].point(lambda p: int(p * alpha))
    out.putalpha(a)
    return out


# ---------------------------------------------------------------------------
# Vertical Configurations (Reels 02 – 07)
# ---------------------------------------------------------------------------

REELS = [
    {
        "id": "02",
        "filename": "eva-reel-02-coffee-bakery-menu",
        "demo": "harbor-street-coffee",
        "dark_status": False,
        "bg_center": "#0f3133",
        "bg_edge": "#041213",
        "grid_tint": (30, 88, 92),
        "accent": "#2bd4b0",
        "cta_text": "#051a15",
        "card_fill": "#131c1e",
        "subcard_fill": "#1b2629",
        "bullet_fill": "#102b2a",
        "coral_bg": "#3b201d",
        "coral_fg": "#f09988",
        "beat1_kicker": "CAFÉS & BAKERIES",
        "beat1_hook": [
            [("Still making customers", False)],
            [("pinch-zoom", True), (" a PDF menu?", False)],
        ],
        "beat1_card_type": "pdf_pain",
        "beat1_tag": "UNREADABLE PDF MENU",
        "beat1_footer": "Customers bounce before finding your location or order link.",
        "beat2_hook": [
            [("Everything customers check,", False)],
            [("on ", False), ("one phone page.", True)],
        ],
        "beat2_items": [
            "Clear espresso & bakery prices",
            "Daily board & fresh bake highlights",
            "Hours & instant Google Maps pin",
            "One-tap Order Ahead or WhatsApp",
        ],
        "beat3_labels": [
            (5.25, 7.35, "01 · FIRST IMPRESSION & PHOTO"),
            (7.45, 9.65, "02 · MENU & PRICES READABLE FAST"),
            (9.75, 11.95, "03 · HOURS, MAP & ORDER LINK"),
        ],
        "beat3_scrolls": ["#menu", "#visit"],
        "beat4_kicker": "DEMO · CAFÉ & BAKERY DESIGN",
        "beat4_title": [
            [("One-page websites for", False)],
            [("cafés & bakeries", True)],
        ],
        "beat4_sub": "Menu, prices, hours & map · Ready in 2 to 3 days",
        "beat4_price": "Starter $50  ·  Core $75  ·  Free mock-up first",
        "beat4_disc": "Demo design only · Fictional business",
    },
    {
        "id": "03",
        "filename": "eva-reel-03-salon-price-list",
        "demo": "linden-and-stone",
        "dark_status": False,
        "bg_center": "#113627",
        "bg_edge": "#05140d",
        "grid_tint": (32, 92, 68),
        "accent": "#35cf99",
        "cta_text": "#051c12",
        "card_fill": "#141d1b",
        "subcard_fill": "#1d2826",
        "bullet_fill": "#102e23",
        "coral_bg": "#3b201d",
        "coral_fg": "#f09988",
        "beat1_kicker": "SALONS & NAIL STUDIOS",
        "beat1_hook": [
            [("Tired of answering", False)],
            [("'how much for nails?'", True), (" in DMs?", False)],
        ],
        "beat1_card_type": "dm_inbox",
        "beat1_tag": "REPETITIVE DM INBOX",
        "beat1_rows": [
            ("Hey! How much for gel manicure & colour?", "2h ago · Still waiting for reply"),
            ("Do you take appointments tomorrow?", "45m ago · No price list linked"),
            ("Where are you located & when do you close?", "12m ago · Missing page info"),
        ],
        "beat1_footer": "Let new clients check prices, hours & book on their own.",
        "beat2_hook": [
            [("Every cut, colour & price,", False)],
            [("ready before ", False), ("they book.", True)],
        ],
        "beat2_items": [
            "Hair, colour & nail price menu",
            "Interactive appointment & stylist picker",
            "Direct Fresha / GlossGenius / WhatsApp link",
            "Ready in 2 to 3 days · From $50",
        ],
        "beat3_labels": [
            (5.25, 7.35, "01 · CALM SALON HERO & HOURS"),
            (7.45, 9.65, "02 · FULL SERVICE & PRICE MENU"),
            (9.75, 11.95, "03 · TAP-TO-BOOK PICKER & TEAM"),
        ],
        "beat3_scrolls": ["#services", "#book"],
        "beat4_kicker": "DEMO · SALON & NAIL STUDIO DESIGN",
        "beat4_title": [
            [("One-page websites for", False)],
            [("salons & nail studios", True)],
        ],
        "beat4_sub": "Service menu, stylists & booking link · 2 to 3 days",
        "beat4_price": "Starter $50  ·  Core $75  ·  Free mock-up first",
        "beat4_disc": "Demo design only · Fictional business",
    },
    {
        "id": "04",
        "filename": "eva-reel-04-barbershop-booking",
        "demo": "northgate-barber-room",
        "dark_status": True,
        "bg_center": "#211c14",
        "bg_edge": "#0a0908",
        "grid_tint": (74, 60, 36),
        "accent": "#e0ac4a",
        "cta_text": "#171209",
        "card_fill": "#19191b",
        "subcard_fill": "#222428",
        "bullet_fill": "#221e17",
        "coral_bg": "#3c211d",
        "coral_fg": "#f09988",
        "beat1_kicker": "BARBERSHOPS",
        "beat1_hook": [
            [("Walk-ins check Google", False)],
            [("before picking a ", False), ("chair.", True)],
        ],
        "beat1_card_type": "maps_search",
        "beat1_tag": "WALK-IN SEARCH ON MAPS",
        "beat1_footer": "New customers pick the next shop with clear prices online.",
        "beat2_hook": [
            [("Shop cuts, fades & booking,", False)],
            [("loaded in ", False), ("one fast tap.", True)],
        ],
        "beat2_items": [
            "Bold cut, skin fade & beard price list",
            "Barbers, walk-in policy & shop hours",
            "Sticky WhatsApp & Book a Chair bar",
            "Built custom for your shop · 2–3 days",
        ],
        "beat3_labels": [
            (5.25, 7.35, "01 · BOLD SHOP HERO & HOURS"),
            (7.45, 9.65, "02 · CLEAR CUT & FADE PRICE LIST"),
            (9.75, 11.95, "03 · BARBERS & ONE-TAP BOOKING"),
        ],
        "beat3_scrolls": ["#prices", "#team"],
        "beat4_kicker": "DEMO · BARBERSHOP DESIGN",
        "beat4_title": [
            [("One-page websites for", False)],
            [("modern barbershops", True)],
        ],
        "beat4_sub": "Cut prices, barbers, walk-in hours & booking · 2–3 days",
        "beat4_price": "Starter $50  ·  Core $75  ·  Free mock-up first",
        "beat4_disc": "Demo design only · Fictional business",
    },
    {
        "id": "05",
        "filename": "eva-reel-05-restaurant-dinner-menu",
        "demo": "saffron-and-salt",
        "dark_status": True,
        "bg_center": "#251a0f",
        "bg_edge": "#0a0806",
        "grid_tint": (82, 58, 24),
        "accent": "#f2a51a",
        "cta_text": "#181005",
        "card_fill": "#191614",
        "subcard_fill": "#23201d",
        "bullet_fill": "#251d13",
        "coral_bg": "#3c211d",
        "coral_fg": "#f09988",
        "beat1_kicker": "RESTAURANTS & GRILLS",
        "beat1_hook": [
            [("Stop sending diners across", False)],
            [("3 links just to read ", False), ("prices.", True)],
        ],
        "beat1_card_type": "three_links",
        "beat1_tag": "3+ LINKS JUST TO CHECK A MENU",
        "beat1_links": [
            ("Link 1", "Main Dishes (Google Slides)"),
            ("Link 2", "Group Trays & Specials PDF"),
            ("Link 3", "DM / Call for Hours & Orders"),
        ],
        "beat1_footer": "Put dishes, prices, map & WhatsApp order on ONE fast page.",
        "beat2_hook": [
            [("Appetizers to mains,", False)],
            [("built for ", False), ("hungry scrollers.", True)],
        ],
        "beat2_items": [
            "Crisp sectioned dishes & clear prices",
            "Signature platter showcase + photos",
            "Sticky Order on WhatsApp & Call bar",
            "Zero monthly fees · Ready in 2–3 days",
        ],
        "beat3_labels": [
            (5.25, 7.35, "01 · MOODY HERO & SPECIALS"),
            (7.45, 9.65, "02 · SECTIONED DISH & PRICE LIST"),
            (9.75, 11.95, "03 · MAP & STICKY WHATSAPP BAR"),
        ],
        "beat3_scrolls": ["#menu", "#visit"],
        "beat4_kicker": "DEMO · RESTAURANT & GRILL DESIGN",
        "beat4_title": [
            [("One-page menu sites for", False)],
            [("independent restaurants", True)],
        ],
        "beat4_sub": "Menu, prices, map & direct order bar · Fixed price",
        "beat4_price": "Starter $50  ·  Core $75  ·  Region B from $50",
        "beat4_disc": "Demo design only · Fictional business",
    },
    {
        "id": "06",
        "filename": "eva-reel-06-established-no-website",
        "demo": "the-copper-kettle",
        "dark_status": False,
        "bg_center": "#10352a",
        "bg_edge": "#05120d",
        "grid_tint": (32, 92, 74),
        "accent": "#35d0a3",
        "cta_text": "#051b14",
        "card_fill": "#141d1c",
        "subcard_fill": "#1c2625",
        "bullet_fill": "#102d25",
        "coral_bg": "#3b201d",
        "coral_fg": "#f09988",
        "beat1_kicker": "ESTABLISHED · NO WEBSITE?",
        "beat1_hook": [
            [("Years of ", False), ("5-star", True), (" reviews", False)],
            [("— still ", False), ("no website?", True)],
        ],
        "beat1_card_type": "established",
        "beat1_tag": "LOVED LOCALLY · NO WEBSITE",
        "beat1_footer": "No multi-page bloat. Keep control of your prices & story.",
        "beat2_hook": [
            [("Custom editorial character.", False)],
            [("Zero ", False), ("copy-paste", True), (" templates.", False)],
        ],
        "beat2_items": [
            "Matches your real shop palette & vibe",
            "Clean sectioned menu & price list",
            "Opening hours, map & table booking",
            "Full ownership · Fixed one-off fee",
        ],
        "beat3_labels": [
            (5.25, 7.35, "01 · BESPOKE BRAND STORY"),
            (7.45, 9.65, "02 · SECTIONED BRUNCH & TEA MENU"),
            (9.75, 11.95, "03 · HOURS, DIRECTIONS & PHOTO"),
        ],
        "beat3_scrolls": ["#menu", "#visit"],
        "beat4_kicker": "DEMO · TEA ROOM & BRUNCH DESIGN",
        "beat4_title": [
            [("Custom character for", False)],
            [("independent local shops", True)],
        ],
        "beat4_sub": "For new or established cafés, restaurants & salons",
        "beat4_price": "Standard $50/$75/$90–$120  ·  Region B $50/$65",
        "beat4_disc": "Demo design only · Fictional business",
    },
]

REEL_07 = {
    "id": "07",
    "filename": "eva-reel-07-before-after-3-step-offer",
    "bg_center": "#0f362a",
    "bg_edge": "#05130d",
    "grid_tint": (30, 92, 72),
    "accent": "#32d4a5",
    "cta_text": "#051b14",
    "beat1_kicker": "LINK-IN-BIO VS OWN PAGE",
    "beat1_hook": [
        [("Why local spots switch from", False)],
        [("link-in-bio", True), (" to 1 clean page.", False)],
    ],
    "before_bullets": [
        "Customers tap 3 links just to hunt down prices",
        "Blurry menu screenshots & outdated hours",
        "You keep replying 'price is $...' in DMs",
    ],
    "after_bullets": [
        "Full menu or service prices readable in 1 second",
        "Live hours, address & Google Maps pin together",
        "Direct Book / Order / WhatsApp tap from day one",
    ],
    "beat2_hook": [
        [("How your ", False), ("free preview", True), (" works.", False)],
    ],
    "steps": [
        ("01", "Send your menu or price list", "A phone photo, PDF, or list is all we need."),
        ("02", "Preview your live page free", "See the real mobile site before spending a dollar."),
        ("03", "Approve & go live in 2–3 days", "1 revision included. Fixed from $50 ($75 up to 30 items)."),
    ],
    "beat3_kicker": "SALONS  ·  BARBERSHOPS  ·  CAFÉS  ·  RESTAURANTS",
    "beat4_kicker": "5 DISTINCT DEMO STYLES · FROM $50",
    "beat4_title": [
        [("One-page websites for", False)],
        [("cafés, salons & barbershops", True)],
    ],
    "beat4_sub": "See a free live preview first · Ready in 2 to 3 days",
    "beat4_price": "From $50 fixed  ·  1 revision included",
    "beat4_disc": "Demo designs only · Businesses shown are fictional",
}


# ---------------------------------------------------------------------------
# Pre-rendered Static Layers per Reel Beat (Zero Outlines!)
# ---------------------------------------------------------------------------

def render_beat1_card_single(cfg: dict) -> Image.Image:
    card_w = 816
    accent = hex_rgb(cfg["accent"])
    card_fill = hex_rgba(cfg["card_fill"], 248)
    sub_fill = hex_rgba(cfg["subcard_fill"], 255)
    coral_bg = hex_rgba(cfg["coral_bg"], 255)
    coral_fg = hex_rgba(cfg["coral_fg"], 255)

    ctype = cfg["beat1_card_type"]
    card_h = 520 if ctype == "dm_inbox" else (472 if ctype in ("maps_search", "three_links", "established") else 460)
    card_bg, pad = make_shadow_box(card_w, card_h, radius=26, fill_rgba=card_fill, shadow_alpha=125, blur=26, dy=14)
    d = ImageDraw.Draw(card_bg)

    # Borderless coral tag at top left (ZERO outline!)
    f_tag = font(FONT_COND_BOLD, 22)
    tag_txt = cfg["beat1_tag"]
    tw = int(f_tag.getlength(tag_txt)) + 34
    tag_x0, tag_y0 = pad + 36, pad + 32
    draw_borderless_pill(card_bg, (tag_x0, tag_y0, tag_x0 + tw, tag_y0 + 42), 21, coral_bg)
    d = ImageDraw.Draw(card_bg)
    d.text((tag_x0 + 17, tag_y0 + 8), tag_txt, font=f_tag, fill=coral_fg)

    ix0, iy0 = pad + 36, tag_y0 + 66
    iw = card_w - 72

    if ctype == "pdf_pain":
        # Ivory blurred-style PDF mock card inside card (ZERO outline!)
        draw_borderless_pill(card_bg, (ix0, iy0, ix0 + iw, iy0 + 250), 20, (242, 237, 226, 255))
        d = ImageDraw.Draw(card_bg)
        bar_col = (163, 159, 151, 255)
        widths = [0.42, 0.54, 0.65, 0.42, 0.52, 0.61]
        for idx, frac in enumerate(widths):
            ry = iy0 + 30 + idx * 34
            lw = int(iw * frac)
            draw_borderless_pill(card_bg, (ix0 + 30, ry, ix0 + 30 + lw, ry + 13), 6, bar_col)
            draw_borderless_pill(card_bg, (ix0 + iw - 125, ry, ix0 + iw - 30, ry + 13), 6, bar_col)
        # Floating dark tooltip pill (ZERO outline!)
        px0, py0 = ix0 + iw - 340, iy0 + 174
        draw_borderless_pill(card_bg, (px0, py0, ix0 + iw - 18, py0 + 62), 16, (26, 30, 34, 255), shadow=True)
        d = ImageDraw.Draw(card_bg)
        d.text((px0 + 24, py0 + 17), "Pinch to read prices...", font=font(FONT_SANS_MED, 23), fill=(242, 240, 235, 255))

    elif ctype == "dm_inbox":
        f_msg = font(FONT_SANS_BOLD, 23)
        f_sub = font(FONT_SANS_REG, 19)
        for idx, (msg, sub) in enumerate(cfg["beat1_rows"]):
            ry0 = iy0 + idx * 100
            draw_borderless_pill(card_bg, (ix0, ry0, ix0 + iw, ry0 + 86), 16, sub_fill)
            d = ImageDraw.Draw(card_bg)
            d.ellipse([ix0 + 18, ry0 + 21, ix0 + 62, ry0 + 65], fill=(56, 66, 71, 255))
            d.text((ix0 + 82, ry0 + 16), msg, font=f_msg, fill=(244, 246, 245, 255))
            d.text((ix0 + 82, ry0 + 49), sub, font=f_sub, fill=(158, 170, 172, 255))

    elif ctype == "maps_search":
        draw_borderless_pill(card_bg, (ix0, iy0, ix0 + iw, iy0 + 258), 20, sub_fill)
        d = ImageDraw.Draw(card_bg)
        f_title = font(FONT_SANS_BOLD, 28)
        lead = "Local Barbershop ·"
        d.text((ix0 + 30, iy0 + 30), lead, font=f_title, fill=(248, 246, 242, 255))
        lw = f_title.getlength(lead)
        draw_star_polygon(d, ix0 + 30 + lw + 22, iy0 + 45, 13, 5.5, (238, 184, 52, 255))
        d.text((ix0 + 30 + lw + 44, iy0 + 30), "4.9 (180+ reviews)", font=f_title, fill=(248, 246, 242, 255))
        d.text((ix0 + 30, iy0 + 74), "Open · Closes 7 PM", font=font(FONT_SANS_MED, 23), fill=(96, 196, 138, 255))

        # Two borderless tonal tags (ZERO outline!)
        cy0 = iy0 + 144
        hw = (iw - 84) // 2
        draw_borderless_pill(card_bg, (ix0 + 30, cy0, ix0 + 30 + hw, cy0 + 66), 33, coral_bg)
        draw_borderless_pill(card_bg, (ix0 + 54 + hw, cy0, ix0 + iw - 30, cy0 + 66), 33, (43, 49, 54, 255))
        d = ImageDraw.Draw(card_bg)
        f_chip = font(FONT_SANS_MED, 22)
        c1, c2 = "Website: None linked", "No cut prices shown"
        d.text((ix0 + 30 + (hw - f_chip.getlength(c1)) / 2, cy0 + 19), c1, font=f_chip, fill=coral_fg)
        d.text((ix0 + 54 + hw + (hw - f_chip.getlength(c2)) / 2, cy0 + 19), c2, font=f_chip, fill=(195, 200, 204, 255))

    elif ctype == "three_links":
        f_tag_l = font(FONT_COND_BOLD, 24)
        f_lbl = font(FONT_SANS_MED, 24)
        for idx, (tag_l, lbl) in enumerate(cfg["beat1_links"]):
            ry0 = iy0 + idx * 88
            draw_borderless_pill(card_bg, (ix0, ry0, ix0 + iw, ry0 + 74), 16, sub_fill)
            d = ImageDraw.Draw(card_bg)
            # Subtle borderless tonal badge on left for Link 1/2/3
            draw_borderless_pill(card_bg, (ix0 + 14, ry0 + 14, ix0 + 114, ry0 + 60), 10, (44, 34, 21, 255))
            d = ImageDraw.Draw(card_bg)
            lw = f_tag_l.getlength(tag_l)
            d.text((ix0 + 14 + (100 - lw) / 2, ry0 + 23), tag_l, font=f_tag_l, fill=(*accent, 255))
            d.text((ix0 + 134, ry0 + 22), lbl, font=f_lbl, fill=(236, 232, 225, 255))

    elif ctype == "established":
        draw_borderless_pill(card_bg, (ix0, iy0, ix0 + iw, iy0 + 258), 20, sub_fill)
        d = ImageDraw.Draw(card_bg)
        d.text((ix0 + 30, iy0 + 26), "Years of loyal neighbourhood regulars —", font=font(FONT_SANS_BOLD, 25), fill=(246, 246, 242, 255))
        d.text((ix0 + 30, iy0 + 68), "but new visitors searching Google only see", font=font(FONT_SANS_REG, 22), fill=(195, 204, 202, 255))
        d.text((ix0 + 30, iy0 + 100), "old menu photos & scattered social posts.", font=font(FONT_SANS_REG, 22), fill=(195, 204, 202, 255))
        draw_borderless_pill(card_bg, (ix0 + 28, iy0 + 162, ix0 + iw - 28, iy0 + 228), 14, (19, 64, 52, 255))
        d = ImageDraw.Draw(card_bg)
        d.text((ix0 + 50, iy0 + 181), "Upgrade to a custom 1-page site · Keep your warm style", font=font(FONT_SANS_MED, 22), fill=(214, 245, 236, 255))

    # Footer explanation line inside card
    d = ImageDraw.Draw(card_bg)
    d.text((pad + 36, pad + card_h - 62), cfg["beat1_footer"], font=font(FONT_SANS_REG, 22), fill=(192, 202, 202, 255))
    return card_bg


def build_single_beat2_list(cfg: dict) -> List[Tuple[Image.Image, int]]:
    """Return 4 borderless elevated cards (staggered animation)."""
    cards = []
    accent = hex_rgb(cfg["accent"])
    card_fill = hex_rgba(cfg["bullet_fill"], 245)
    cw, ch = 780, 96
    f_item = font(FONT_SANS_MED, 28)

    for text in cfg["beat2_items"]:
        box, pad = make_shadow_box(cw, ch, radius=22, fill_rgba=card_fill, shadow_alpha=75, blur=16, dy=8)
        d = ImageDraw.Draw(box)
        # Solid small accent circle indicator (no outline!)
        cy = pad + ch // 2
        d.ellipse([pad + 30, cy - 16, pad + 62, cy + 16], fill=(*accent, 44))
        draw_checkmark(d, pad + 46, cy, 18, (*accent, 255), width=4)
        d.text((pad + 86, cy - 17), text, font=f_item, fill=(244, 246, 245, 255))
        cards.append((box, pad))
    return cards


def build_reel07_beat1_panels(cfg: dict) -> Tuple[Image.Image, Image.Image, int]:
    """Borderless BEFORE panel + Borderless AFTER panel with vector cross & check icons."""
    pw, ph = 860, 326
    accent = hex_rgb(cfg["accent"])

    # BEFORE card (muted warm charcoal-umber surface, zero outline!)
    before, pad = make_shadow_box(pw, ph, radius=24, fill_rgba=(34, 23, 22, 245), shadow_alpha=110, blur=24, dy=12)
    draw_borderless_pill(before, (pad + 34, pad + 30, pad + 150, pad + 72), 12, (74, 34, 31, 255))
    db = ImageDraw.Draw(before)
    db.text((pad + 54, pad + 38), "BEFORE", font=font(FONT_COND_BOLD, 24), fill=(244, 160, 146, 255))
    db.text((pad + 174, pad + 35), "Link-in-bio + DM guesses", font=font(FONT_SANS_BOLD, 30), fill=(248, 246, 244, 255))

    f_bul = font(FONT_SANS_REG, 24)
    for i, line in enumerate(cfg["before_bullets"]):
        ry = pad + 114 + i * 62
        draw_cross(db, pad + 52, ry + 13, 18, (235, 118, 98, 255), width=4)
        db.text((pad + 86, ry - 2), line, font=f_bul, fill=(214, 206, 204, 255))

    # AFTER card (deep emerald surface, zero outline!)
    after, pad2 = make_shadow_box(pw, ph, radius=24, fill_rgba=(14, 48, 39, 248), shadow_alpha=115, blur=24, dy=12)
    draw_borderless_pill(after, (pad2 + 34, pad2 + 30, pad2 + 138, pad2 + 72), 12, (20, 82, 63, 255))
    da = ImageDraw.Draw(after)
    da.text((pad2 + 52, pad2 + 38), "AFTER", font=font(FONT_COND_BOLD, 24), fill=(*accent, 255))
    da.text((pad2 + 162, pad2 + 35), "One clean mobile-first site", font=font(FONT_SANS_BOLD, 30), fill=(248, 250, 248, 255))

    for i, line in enumerate(cfg["after_bullets"]):
        ry = pad2 + 114 + i * 62
        draw_checkmark(da, pad2 + 52, ry + 14, 20, (*accent, 255), width=4)
        da.text((pad2 + 86, ry - 2), line, font=f_bul, fill=(235, 242, 240, 255))

    return before, after, pad


def build_reel07_beat2_steps(cfg: dict) -> List[Tuple[Image.Image, int]]:
    """3 borderless step cards for Reel 07 Beat 2 (zero outline!)."""
    out = []
    cw, ch = 856, 154
    accent = hex_rgb(cfg["accent"])
    for num, title, desc in cfg["steps"]:
        card, pad = make_shadow_box(cw, ch, radius=24, fill_rgba=(16, 44, 36, 246), shadow_alpha=105, blur=20, dy=10)
        draw_borderless_pill(card, (pad + 34, pad + 39, pad + 110, pad + 115), 20, (*accent, 255))
        d = ImageDraw.Draw(card)
        fn = font(FONT_COND_BOLD, 32)
        nw = fn.getlength(num)
        d.text((pad + 34 + (76 - nw) / 2, pad + 58), num, font=fn, fill=(6, 28, 21, 255))
        d.text((pad + 140, pad + 38), title, font=font(FONT_SANS_BOLD, 29), fill=(248, 250, 248, 255))
        d.text((pad + 140, pad + 82), desc, font=font(FONT_SANS_REG, 22), fill=(192, 210, 205, 255))
        out.append((card, pad))
    return out


def build_beat4_footer_block(cfg: dict, is_reel07: bool = False) -> Image.Image:
    """
    Build clean borderless Beat 4 & Cover bottom text + pricing strip + EC + CTA + disclaimer.
    Zero perimeter outlines on ANY pill, price box, monogram, or CTA!
    Keeps all elements cleanly inside Instagram's 3:4 profile-grid center crop [240..1680].
    """
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    accent = hex_rgb(cfg["accent"])
    cta_fg = hex_rgba(cfg["cta_text"], 255)
    d = ImageDraw.Draw(layer)

    y_after = draw_mixed_serif_headline(d, 1126, cfg["beat4_title"], size=58, line_gap=10, accent_rgb=accent)

    # Subtitle
    f_sub = font(FONT_SANS_REG, 27)
    sub = cfg["beat4_sub"]
    sw = f_sub.getlength(sub)
    d.text(((W - sw) / 2, y_after + 14), sub, font=f_sub, fill=(214, 222, 220, 255))

    # Price badge — clean borderless tonal strip (ZERO outline!)
    f_pr = font(FONT_SANS_BOLD, 26)
    pr_txt = cfg["beat4_price"]
    pw = int(f_pr.getlength(pr_txt)) + 64
    py0 = y_after + 68
    px0 = (W - pw) // 2
    strip_bg = (34, 28, 19, 255) if not is_reel07 and cfg.get("id") in ("04", "05") else (14, 43, 35, 255)
    draw_borderless_pill(layer, (px0, py0, px0 + pw, py0 + 54), 16, strip_bg, shadow=True)
    d = ImageDraw.Draw(layer)
    d.text((px0 + 32, py0 + 12), pr_txt, font=f_pr, fill=(246, 248, 247, 255))

    # EC monogram + Link in bio CTA (BOTH strictly borderless!)
    cy0 = py0 + 82
    cta_txt = "Link in bio · @evacheecks"
    f_cta = font(FONT_SANS_BOLD, 28)
    cta_w = int(f_cta.getlength(cta_txt)) + 78
    ec_d = 76
    gap = 20
    total_w = ec_d + gap + cta_w
    sx = (W - total_w) // 2

    ec_bg = (42, 34, 22, 255) if not is_reel07 and cfg.get("id") in ("04", "05") else (19, 59, 48, 255)
    draw_borderless_pill(layer, (sx, cy0, sx + ec_d, cy0 + ec_d), ec_d // 2, ec_bg, shadow=True)
    draw_borderless_pill(layer, (sx + ec_d + gap, cy0, sx + total_w, cy0 + ec_d), ec_d // 2, (*accent, 255), shadow=True)

    d = ImageDraw.Draw(layer)
    f_ec = font(FONT_COND_BOLD, 28)
    ec_w = f_ec.getlength("EC")
    d.text((sx + (ec_d - ec_w) / 2, cy0 + 22), "EC", font=f_ec, fill=(244, 246, 245, 255))
    d.text((sx + ec_d + gap + 39, cy0 + 21), cta_txt, font=f_cta, fill=cta_fg)

    # Fictional disclaimer
    f_disc = font(FONT_SANS_REG, 22)
    disc = cfg["beat4_disc"]
    dw = f_disc.getlength(disc)
    d.text(((W - dw) / 2, cy0 + ec_d + 28), disc, font=f_disc, fill=(148, 160, 158, 255))
    return layer


# ---------------------------------------------------------------------------
# Audio Synthesis (-26 dB stereo warm electric piano pad)
# ---------------------------------------------------------------------------

def synthesize_ambient_wav(out_wav: Path, duration: float = DURATION_SEC, seed: int = 42) -> None:
    """
    Generate a clean 44.1 kHz stereo ambient electric-piano chord pad (Cmaj9 -> Am9 -> Fmaj9 -> G6),
    matching gentle background lo-fi feel around -26 dB mean with smooth fade in/out.
    """
    sr = 44100
    n = int(sr * duration)
    t = np.linspace(0.0, duration, n, endpoint=False)

    # Frequencies in Hz for warm voicings
    chords = [
        [261.63, 329.63, 392.00, 493.88, 587.33],  # Cmaj9
        [220.00, 261.63, 329.63, 392.00, 493.88],  # Am9
        [174.61, 220.00, 261.63, 329.63, 392.00],  # Fmaj9
        [196.00, 246.94, 293.66, 329.63, 440.00],  # G6
    ]
    bar_len = duration / 4.0
    left = np.zeros(n, dtype=np.float64)
    right = np.zeros(n, dtype=np.float64)

    for b_idx, notes in enumerate(chords):
        t0 = b_idx * bar_len
        t1 = t0 + bar_len
        loc = t - t0
        # Soft envelope overlapping seamlessly between chords
        att = np.clip(loc / 0.45, 0.0, 1.0)
        rel = np.clip((t1 + 0.55 - t) / 0.90, 0.0, 1.0)
        active = (t >= t0) & (t < t1 + 0.55)
        env = np.where(active, att * np.minimum(1.0, rel) * np.exp(-np.maximum(0.0, loc) * 0.24), 0.0)

        for k, freq in enumerate(notes):
            pan = 0.5 + 0.24 * math.sin(seed + k * 1.3 + b_idx * 0.7)
            detune = 1.0 + 0.0018 * (1 if k % 2 == 0 else -1)
            tone = (
                0.70 * np.sin(2.0 * math.pi * freq * t)
                + 0.20 * np.sin(2.0 * math.pi * freq * 2.0 * detune * t + 0.4)
                + 0.06 * np.sin(2.0 * math.pi * freq * 3.0 * t + 1.1)
            )
            sig = tone * env * (0.20 if k < 2 else 0.14)
            left += sig * (1.0 - pan * 0.5)
            right += sig * (0.5 + pan * 0.5)

    # Soft global fade in/out + target ~ -26 dB RMS
    gf_in = np.clip(t / 0.85, 0.0, 1.0)
    gf_out = np.clip((duration - t) / 1.10, 0.0, 1.0)
    stereo = np.stack([left, right], axis=1) * (gf_in * gf_out)[:, None]

    rms = math.sqrt(float(np.mean(stereo ** 2))) or 1.0
    target_rms = 10.0 ** (-26.2 / 20.0)  # ~0.049 => ~ -26.2 dBFS RMS
    stereo = np.clip(stereo * (target_rms / rms), -0.85, 0.85)
    pcm = (stereo * 32767.0).astype(np.int16)

    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


# ---------------------------------------------------------------------------
# Compositor per Reel
# ---------------------------------------------------------------------------

def render_single_reel(cfg: dict, shots_dir: Path, meta: dict, out_dir: Path, preview_frames: bool = False) -> Tuple[Path, Path]:
    slug = cfg["demo"]
    name = cfg["filename"]
    print(f"\n=== Rendering Reel {cfg['id']} ({name}) ===")

    bg_base = build_background(cfg["bg_center"], cfg["bg_edge"], cfg["grid_tint"])
    accent = hex_rgb(cfg["accent"])

    # Build demo phone mockups at two crisp sizes:
    # Beat 3 active demo phone (468 x 964) & Beat 4 cover compact phone (384 x 788)
    phone_b3 = DemoAsset(slug, cfg["dark_status"], shots_dir, 456, 944, meta[slug])
    phone_b4 = DemoAsset(slug, cfg["dark_status"], shots_dir, 376, 774, meta[slug])

    # Static overlays
    # Beat 1
    b1_header = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_kicker(b1_header, 290, cfg["beat1_kicker"], accent, show_dot=True)
    draw_mixed_serif_headline(ImageDraw.Draw(b1_header), 344, cfg["beat1_hook"], size=62, line_gap=14, accent_rgb=accent)
    b1_card = render_beat1_card_single(cfg)

    # Beat 2
    b2_header = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_mixed_serif_headline(ImageDraw.Draw(b2_header), 312, cfg["beat2_hook"], size=62, line_gap=14, accent_rgb=accent)
    b2_cards = build_single_beat2_list(cfg)

    # Beat 3 labels (pre-drawn to avoid repeating per frame)
    b3_label_layers = []
    for t0, t1, lbl in cfg["beat3_labels"]:
        ly = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw_kicker(ly, 326, lbl, accent, show_dot=True, font_size=24, tracking=3.5)
        b3_label_layers.append((t0, t1, ly))

    # Beat 4 & Cover static render (100% deterministic hero)
    cover_frame = bg_base.copy()
    draw_kicker(cover_frame, 246, cfg["beat4_kicker"], accent, show_dot=True)
    p4_hero = phone_b4.render_phone(0.0)
    paste_centered(cover_frame, p4_hero, 692)
    b4_footer = build_beat4_footer_block(cfg, is_reel07=False)
    cover_frame.alpha_composite(b4_footer)

    cover_path = out_dir / f"{name}-cover.png"
    cover_frame.convert("RGB").save(cover_path, "PNG", optimize=True)

    # Compute scroll milestones for Beat 3 (5.25s -> 11.95s)
    y_hero = 0.0
    y_mid = float(phone_b3.css_offset(cfg["beat3_scrolls"][0], 900))
    y_bot = float(phone_b3.css_offset(cfg["beat3_scrolls"][1], 1800))
    # Ensure bottom never cuts awkwardly and covers rich lower block
    y_bot = min(float(phone_b3.max_scroll), max(y_bot, y_mid + 300.0))

    # Synthesize audio WAV
    wav_path = out_dir / f"{name}.wav"
    synthesize_ambient_wav(wav_path, DURATION_SEC, seed=int(cfg["id"]) * 13)

    mp4_path = out_dir / f"{name}.mp4"
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{W}x{H}", "-pix_fmt", "rgb24", "-r", str(FPS),
        "-i", "pipe:0",
        "-i", str(wav_path),
        "-c:v", "libx264", "-profile:v", "high", "-level:v", "4.1",
        "-pix_fmt", "yuv420p", "-crf", "17", "-preset", "medium",
        "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-shortest",
        "-loglevel", "error",
        str(mp4_path),
    ]
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None

    for fi in range(TOTAL_FRAMES):
        t = fi / float(FPS)
        frame = bg_base.copy()

        # Beat 1: 0.00 -> 2.65 (clean dip to bg over 2.50 -> 2.65)
        if t < 2.65:
            a_in = ease_out_cubic(t / 0.28)
            a_out = ease_out_cubic((2.65 - t) / 0.16) if t > 2.49 else 1.0
            a = min(a_in, a_out)
            if a > 0.005:
                dy = int(round((1.0 - ease_out_cubic(t / 0.35)) * 22))
                frame.alpha_composite(apply_alpha(b1_header, a), (0, dy))
                c_a = ease_out_cubic(max(0.0, t - 0.10) / 0.32) * a_out
                cdy = int(round((1.0 - ease_out_cubic(max(0.0, t - 0.10) / 0.40)) * 28))
                paste_centered(frame, apply_alpha(b1_card, c_a), 788 + cdy)

        # Beat 2: 2.65 -> 5.25
        elif t < 5.25:
            lt = t - 2.65
            a_in = ease_out_cubic(lt / 0.20)
            a_out = ease_out_cubic((5.25 - t) / 0.16) if t > 5.09 else 1.0
            a = min(a_in, a_out)
            if a > 0.005:
                dy = int(round((1.0 - ease_out_cubic(lt / 0.28)) * 18))
                frame.alpha_composite(apply_alpha(b2_header, a), (0, dy))
                for idx, (box, _) in enumerate(b2_cards):
                    st = 0.08 + idx * 0.13
                    ca = ease_out_cubic((lt - st) / 0.26) * a_out
                    if ca > 0.005:
                        cdy = int(round((1.0 - ease_out_cubic((lt - st) / 0.30)) * 24))
                        paste_centered(frame, apply_alpha(box, ca), 590 + idx * 124 + cdy)

        # Beat 3: 5.25 -> 11.95
        elif t < 11.95:
            lt = t - 5.25
            a_in = ease_out_cubic(lt / 0.22)
            a_out = ease_out_cubic((11.95 - t) / 0.16) if t > 11.79 else 1.0
            a = min(a_in, a_out)
            if a > 0.005:
                # Section caption transitions cleanly without colliding headlines
                for t0, t1, ly in b3_label_layers:
                    if t0 <= t < t1:
                        la = min(ease_out_cubic((t - t0) / 0.14), ease_out_cubic((t1 - t) / 0.12))
                        frame.alpha_composite(apply_alpha(ly, la * a_out))

                # Smooth segmented scroll across Hero -> Menu/Services -> Book/Visit
                if t < 6.45:
                    sy_scroll = lerp(y_hero, y_hero + 65.0, (t - 5.25) / 1.20)
                elif t < 7.60:
                    sy_scroll = lerp(y_hero + 65.0, y_mid, ease_in_out_cubic((t - 6.45) / 1.15))
                elif t < 8.45:
                    sy_scroll = lerp(y_mid, y_mid + 24.0, (t - 7.60) / 0.85)
                elif t < 9.35:
                    sy_scroll = lerp(y_mid + 24.0, y_mid + 160.0, (t - 8.45) / 0.90)
                elif t < 10.50:
                    sy_scroll = lerp(y_mid + 160.0, y_bot, ease_in_out_cubic((t - 9.35) / 1.15))
                else:
                    end_pad = min(float(phone_b3.max_scroll), y_bot + 140.0)
                    sy_scroll = lerp(y_bot, end_pad, (t - 10.50) / 1.45)

                pdy = int(round((1.0 - ease_out_cubic(lt / 0.35)) * 28))
                ph_img = phone_b3.render_phone(sy_scroll, alpha_mult=a)
                paste_centered(frame, ph_img, 965 + pdy)

        # Beat 4: 11.95 -> 15.00
        else:
            lt = t - 11.95
            a = ease_out_cubic(lt / 0.24)
            if a >= 0.999:
                frame = cover_frame
            else:
                frame = Image.alpha_composite(bg_base, apply_alpha(cover_frame, a))

        proc.stdin.write(frame.convert("RGB").tobytes())

    proc.stdin.close()
    ret = proc.wait()
    wav_path.unlink(missing_ok=True)
    if ret != 0:
        raise RuntimeError(f"ffmpeg failed for Reel {cfg['id']} with code {ret}")
    print(f"Saved {mp4_path} ({mp4_path.stat().st_size // 1024} KB) + {cover_path.name}")
    return mp4_path, cover_path


def render_reel07(shots_dir: Path, meta: dict, out_dir: Path) -> Tuple[Path, Path]:
    cfg = REEL_07
    name = cfg["filename"]
    print(f"\n=== Rendering Reel 07 ({name}) ===")

    bg_base = build_background(cfg["bg_center"], cfg["bg_edge"], cfg["grid_tint"])
    accent = hex_rgb(cfg["accent"])

    # Static Beat 1 header + comparison panels
    b1_header = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_kicker(b1_header, 290, cfg["beat1_kicker"], accent, show_dot=True)
    draw_mixed_serif_headline(ImageDraw.Draw(b1_header), 344, cfg["beat1_hook"], size=60, line_gap=12, accent_rgb=accent)
    before_panel, after_panel, _ = build_reel07_beat1_panels(cfg)

    # Static Beat 2 header + 3 step cards
    b2_header = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_mixed_serif_headline(ImageDraw.Draw(b2_header), 312, cfg["beat2_hook"], size=62, line_gap=14, accent_rgb=accent)
    b2_steps = build_reel07_beat2_steps(cfg)

    # Beat 3 & 4 3-Phone Triple Android Showcase assets
    # Left tilted (-5 deg): Linden & Stone | Center upright: Northgate | Right tilted (+5 deg): Harbor Street
    linden_b3 = DemoAsset("linden-and-stone", False, shots_dir, 344, 712, meta["linden-and-stone"])
    north_b3 = DemoAsset("northgate-barber-room", True, shots_dir, 368, 760, meta["northgate-barber-room"])
    harbor_b3 = DemoAsset("harbor-street-coffee", False, shots_dir, 344, 712, meta["harbor-street-coffee"])

    b3_header = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_kicker(b3_header, 310, cfg["beat3_kicker"], accent, show_dot=False, font_size=24, tracking=3.0)

    # Prebuild Beat 4 Cover (Triple Hero Fan + End Copy + CTA)
    linden_b4 = DemoAsset("linden-and-stone", False, shots_dir, 310, 642, meta["linden-and-stone"])
    north_b4 = DemoAsset("northgate-barber-room", True, shots_dir, 330, 684, meta["northgate-barber-room"])
    harbor_b4 = DemoAsset("harbor-street-coffee", False, shots_dir, 310, 642, meta["harbor-street-coffee"])

    cover_frame = bg_base.copy()
    draw_kicker(cover_frame, 246, cfg["beat4_kicker"], accent, show_dot=True, font_size=22, tracking=3.2)

    p_left = linden_b4.render_phone(0.0).rotate(5.5, resample=Image.Resampling.BICUBIC, expand=True)
    p_right = harbor_b4.render_phone(0.0).rotate(-5.5, resample=Image.Resampling.BICUBIC, expand=True)
    p_center = north_b4.render_phone(0.0)

    def paste_xy(dest: Image.Image, ov: Image.Image, cx: int, cy: int) -> None:
        dest.alpha_composite(ov, (int(cx - ov.width / 2), int(cy - ov.height / 2)))

    paste_xy(cover_frame, p_left, 238, 706)
    paste_xy(cover_frame, p_right, 842, 706)
    paste_xy(cover_frame, p_center, 540, 680)

    b4_footer = build_beat4_footer_block(cfg, is_reel07=True)
    cover_frame.alpha_composite(b4_footer)
    cover_path = out_dir / f"{name}-cover.png"
    cover_frame.convert("RGB").save(cover_path, "PNG", optimize=True)

    # Beat 3 scroll ranges (services/prices/menu -> visit)
    l_s0, l_s1 = float(linden_b3.css_offset("#services", 1400)), float(linden_b3.css_offset("#book", 2800))
    n_s0, n_s1 = float(north_b3.css_offset("#prices", 950)), float(north_b3.css_offset("#visit", 3900))
    h_s0, h_s1 = float(harbor_b3.css_offset("#menu", 1100)), float(harbor_b3.css_offset("#visit", 2100))

    wav_path = out_dir / f"{name}.wav"
    synthesize_ambient_wav(wav_path, DURATION_SEC, seed=91)

    mp4_path = out_dir / f"{name}.mp4"
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{W}x{H}", "-pix_fmt", "rgb24", "-r", str(FPS),
        "-i", "pipe:0",
        "-i", str(wav_path),
        "-c:v", "libx264", "-profile:v", "high", "-level:v", "4.1",
        "-pix_fmt", "yuv420p", "-crf", "17", "-preset", "medium",
        "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-shortest",
        "-loglevel", "error",
        str(mp4_path),
    ]
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None

    for fi in range(TOTAL_FRAMES):
        t = fi / float(FPS)
        frame = bg_base.copy()

        # Beat 1: 0.00 -> 3.00 (BEFORE vs AFTER)
        if t < 3.00:
            a_in = ease_out_cubic(t / 0.28)
            a_out = ease_out_cubic((3.00 - t) / 0.16) if t > 2.84 else 1.0
            a = min(a_in, a_out)
            if a > 0.005:
                dy = int(round((1.0 - ease_out_cubic(t / 0.34)) * 20))
                frame.alpha_composite(apply_alpha(b1_header, a), (0, dy))
                ca1 = ease_out_cubic((t - 0.10) / 0.28) * a_out
                ca2 = ease_out_cubic((t - 0.26) / 0.28) * a_out
                if ca1 > 0.005:
                    paste_centered(frame, apply_alpha(before_panel, ca1), 716 + int((1 - ease_out_cubic((t - 0.10) / 0.3)) * 20))
                if ca2 > 0.005:
                    paste_centered(frame, apply_alpha(after_panel, ca2), 1076 + int((1 - ease_out_cubic((t - 0.26) / 0.3)) * 20))

        # Beat 2: 3.00 -> 6.00 (01 -> 02 -> 03 Free Preview)
        elif t < 6.00:
            lt = t - 3.00
            a_in = ease_out_cubic(lt / 0.20)
            a_out = ease_out_cubic((6.00 - t) / 0.16) if t > 5.84 else 1.0
            a = min(a_in, a_out)
            if a > 0.005:
                frame.alpha_composite(apply_alpha(b2_header, a))
                for idx, (card, _) in enumerate(b2_steps):
                    st = 0.06 + idx * 0.42
                    ca = ease_out_cubic((lt - st) / 0.28) * a_out
                    if ca > 0.005:
                        cdy = int(round((1.0 - ease_out_cubic((lt - st) / 0.30)) * 26))
                        paste_centered(frame, apply_alpha(card, ca), 590 + idx * 182 + cdy)

        # Beat 3: 6.00 -> 11.95 (3-Phone Android Interactive Showcase)
        elif t < 11.95:
            lt = t - 6.00
            a_in = ease_out_cubic(lt / 0.22)
            a_out = ease_out_cubic((11.95 - t) / 0.16) if t > 11.79 else 1.0
            a = min(a_in, a_out)
            if a > 0.005:
                frame.alpha_composite(apply_alpha(b3_header, a))
                # Scroll progress across Beat 3: hero hold 0.7s, then slow continuous scroll through menus -> visit
                if lt < 0.80:
                    prog = 0.0
                else:
                    prog = ease_in_out_cubic((lt - 0.80) / (5.95 - 0.80))

                pl = linden_b3.render_phone(lerp(l_s0 - 300, l_s1, prog), alpha_mult=a).rotate(5.5, resample=Image.Resampling.BICUBIC, expand=True)
                pr = harbor_b3.render_phone(lerp(h_s0 - 200, h_s1, prog), alpha_mult=a).rotate(-5.5, resample=Image.Resampling.BICUBIC, expand=True)
                pc = north_b3.render_phone(lerp(n_s0 - 240, n_s1, prog), alpha_mult=a)

                pdy = int(round((1.0 - ease_out_cubic(lt / 0.32)) * 28))
                paste_xy(frame, pl, 224, 965 + pdy)
                paste_xy(frame, pr, 856, 965 + pdy)
                paste_xy(frame, pc, 540, 932 + pdy)

        # Beat 4: 11.95 -> 15.00
        else:
            lt = t - 11.95
            a = ease_out_cubic(lt / 0.24)
            if a >= 0.999:
                frame = cover_frame
            else:
                frame = Image.alpha_composite(bg_base, apply_alpha(cover_frame, a))

        proc.stdin.write(frame.convert("RGB").tobytes())

    proc.stdin.close()
    ret = proc.wait()
    wav_path.unlink(missing_ok=True)
    if ret != 0:
        raise RuntimeError(f"ffmpeg failed for Reel 07 with code {ret}")
    print(f"Saved {mp4_path} ({mp4_path.stat().st_size // 1024} KB) + {cover_path.name}")
    return mp4_path, cover_path


def run_preflight_glyph_check() -> None:
    """Verify zero tofu/missing glyphs across every text string in all 6 Reels."""
    all_texts: List[str] = []
    for cfg in REELS:
        all_texts.extend([
            cfg["beat1_kicker"], cfg["beat1_tag"], cfg["beat1_footer"],
            cfg["beat4_kicker"], cfg["beat4_sub"], cfg["beat4_price"], cfg["beat4_disc"],
        ])
        all_texts.extend(cfg["beat2_items"])
        for _, _, lbl in cfg["beat3_labels"]:
            all_texts.append(lbl)
        for segs in cfg["beat1_hook"] + cfg["beat2_hook"] + cfg["beat4_title"]:
            for txt, _ in segs:
                all_texts.append(txt)
    all_texts.extend(REEL_07["before_bullets"] + REEL_07["after_bullets"])
    for _, t, desc in REEL_07["steps"]:
        all_texts.extend([t, desc])

    # Check Latin + punctuation glyphs in P052-Bold and Roboto-Medium
    f_serif = font(FONT_SERIF_BOLD, 40)
    f_sans = font(FONT_SANS_MED, 28)
    for txt in all_texts:
        for ch in txt:
            if ch in (" ", "\n", "\t"):
                continue
            if not f_sans.getmask(ch).getbbox() and not f_serif.getmask(ch).getbbox():
                raise RuntimeError(f"Missing glyph {ch!r} in text: {txt!r}")
    print("Preflight glyph check PASSED (0 missing glyphs).")


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate borderless Instagram Reels 02–07 & covers")
    ap.add_argument("--shots-dir", type=Path, default=DEFAULT_SHOTS_DIR, help="Directory holding demo_* screenshots + meta.json")
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Output directory for MP4s + cover PNGs")
    ap.add_argument("--only", nargs="*", help="Render only specific reel IDs (e.g. 02 07)")
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    run_preflight_glyph_check()

    meta_path = args.shots_dir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"Missing {meta_path}. Capture updated demo screenshots first.")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    target_ids = set(args.only) if args.only else {"02", "03", "04", "05", "06", "07"}
    for cfg in REELS:
        if cfg["id"] in target_ids:
            render_single_reel(cfg, args.shots_dir, meta, args.out_dir)
    if "07" in target_ids:
        render_reel07(args.shots_dir, meta, args.out_dir)

    print(f"\nAll requested Reels finished in {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
