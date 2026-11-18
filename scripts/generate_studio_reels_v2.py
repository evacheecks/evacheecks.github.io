#!/usr/bin/env python3
"""
Studio-Quality Instagram Reels Generator (Reels 08–13, for 6 daily @evacheecks uploads).

Features genuine optical motion blur & studio motion design:
- Dual-stage cinema motion blur:
  1) Fast 2-pass continuous premultiplied directional velocity blur (zero stepping artifacts)
  2) Physical shutter-angle temporal multi-sampling (5-7 sub-frames) accumulated in gamma-decoded
     linear light via precomputed LUTs during high-velocity transitions & kinetic gestures
- Continuous whip-pan / Z-depth camera transitions (zero boring fade-to-bg cuts)
- Masked kinetic typography reveals + elastic spring overshoot physics
- Living volumetric studio backdrop (drifting soft key/rim light orbs + subtle anti-banding film grain)
- Generic dark-graphite punch-hole Android mockup ONLY (Entry 13) with diagonal specular glass sweep
- Live interactive touch cursor, expanding ripple rings, flick-scroll physics, and real live booking taps
- Synced bespoke stereo felt-piano/Rhodes beds + cinematic whip-whooshes + tactile UI tap chimes
- Strict DESIGN-RULES.md compliance: ZERO perimeter borders/outlines on cards/pills/chips/buttons,
  ZERO headline biscuit pills, 3:4 IG profile-grid safe-zone cover/end-cards [y=240..1680].
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import math
import subprocess
import sys
import time
import wave
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
FPS = 30
DURATION_SEC = 15.0
TOTAL_FRAMES = int(FPS * DURATION_SEC)

DEFAULT_SHOTS_DIR = Path("/tmp/demo_shots_v2")
DEFAULT_OUT_DIR = Path("/tmp/reels_studio_v2")

# Crisp installed system fonts
FONT_SERIF_BOLD = "/usr/share/fonts/opentype/urw-base35/P052-Bold.otf"
FONT_SERIF_BI = "/usr/share/fonts/opentype/urw-base35/P052-BoldItalic.otf"
FONT_SANS_REG = "/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/Roboto-Regular.ttf"
FONT_SANS_MED = "/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/Roboto-Medium.ttf"
FONT_SANS_BOLD = "/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/Roboto-Bold.ttf"
FONT_SANS_BLACK = "/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/Roboto-Black.ttf"
FONT_COND_BOLD = "/usr/share/fonts/truetype/roboto/unhinted/RobotoCondensed-Bold.ttf"

# Fast LUTs for accurate linear-light optical shutter accumulation
_SRGB_TO_LIN = (np.arange(256, dtype=np.float32) / 255.0) ** 2.2
_LIN_TO_SRGB = np.clip((np.linspace(0.0, 1.0, 4096, dtype=np.float32) ** (1.0 / 2.2)) * 255.0 + 0.5, 0, 255).astype(np.uint8)

_FONT_CACHE: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    key = (path, int(size))
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = ImageFont.truetype(path, int(size))
    return _FONT_CACHE[key]


# ---------------------------------------------------------------------------
# Easing & Physics Curves
# ---------------------------------------------------------------------------
def clamp01(x: float) -> float:
    return 0.0 if x <= 0.0 else (1.0 if x >= 1.0 else x)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def ease_out_expo(t: float) -> float:
    t = clamp01(t)
    return 1.0 if t >= 1.0 else 1.0 - (2.0 ** (-10.0 * t))


def ease_in_cubic(t: float) -> float:
    t = clamp01(t)
    return t * t * t


def ease_out_cubic(t: float) -> float:
    t = clamp01(t)
    return 1.0 - (1.0 - t) ** 3


def ease_in_out_cubic(t: float) -> float:
    t = clamp01(t)
    return 4.0 * t * t * t if t < 0.5 else 1.0 - ((-2.0 * t + 2.0) ** 3) / 2.0


def ease_in_out_quint(t: float) -> float:
    t = clamp01(t)
    return 16.0 * (t ** 5) if t < 0.5 else 1.0 - ((-2.0 * t + 2.0) ** 5) / 2.0


def ease_out_back(t: float, s: float = 1.45) -> float:
    t = clamp01(t)
    u = t - 1.0
    return 1.0 + (s + 1.0) * (u ** 3) + s * (u ** 2)


def ease_spring(t: float, freq: float = 1.85, decay: float = 6.2) -> float:
    t = clamp01(t)
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return 1.0 - math.exp(-decay * t) * math.cos(freq * math.pi * t)


def hex_rgb(value: str) -> Tuple[int, int, int]:
    h = value.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def hex_rgba(value: str, alpha: int = 255) -> Tuple[int, int, int, int]:
    r, g, b = hex_rgb(value)
    return (r, g, b, alpha)


# ---------------------------------------------------------------------------
# Optical Motion Blur Primitives (Continuous Directional + Linear Shutter)
# ---------------------------------------------------------------------------
def _box_blur_1d_premul(arr: np.ndarray, radius: int, axis: int) -> np.ndarray:
    """Exact O(N) 1D box blur via cumsum along axis=0 (vertical) or axis=1 (horizontal)."""
    if radius <= 0:
        return arr
    k = 2 * radius + 1
    if axis == 0:
        pad = np.pad(arr, ((radius, radius), (0, 0), (0, 0)), mode="constant", constant_values=0.0)
        cs = np.cumsum(pad, axis=0)
        out = np.empty_like(arr)
        out[0] = cs[k - 1]
        out[1:] = cs[k:] - cs[:-k]
        return out / float(k)
    else:
        pad = np.pad(arr, ((0, 0), (radius, radius), (0, 0)), mode="constant", constant_values=0.0)
        cs = np.cumsum(pad, axis=1)
        out = np.empty_like(arr)
        out[:, 0] = cs[:, k - 1]
        out[:, 1:] = cs[:, k:] - cs[:, :-k]
        return out / float(k)


def directional_blur_rgba(img: Image.Image, dx: float = 0.0, dy: float = 0.0) -> Image.Image:
    """
    Continuous cinema-grade 2-pass premultiplied directional motion blur along X and/or Y.
    Zero discrete stepping artifacts; automatically pads edges cleanly so streaks never clip!
    """
    rx = int(round(min(68.0, abs(dx) * 0.42)))
    ry = int(round(min(68.0, abs(dy) * 0.42)))
    if rx < 2 and ry < 2:
        return img

    arr = np.asarray(img, dtype=np.float32)
    alpha = arr[..., 3:4] / 255.0
    premul = np.empty_like(arr)
    premul[..., :3] = arr[..., :3] * alpha
    premul[..., 3:4] = arr[..., 3:4]

    if ry >= 2:
        # 2-pass box = smooth triangular optical shutter profile
        r1 = max(1, ry // 2)
        premul = _box_blur_1d_premul(premul, r1, axis=0)
        premul = _box_blur_1d_premul(premul, max(1, ry - r1), axis=0)
    if rx >= 2:
        r1 = max(1, rx // 2)
        premul = _box_blur_1d_premul(premul, r1, axis=1)
        premul = _box_blur_1d_premul(premul, max(1, rx - r1), axis=1)

    a_out = premul[..., 3:4]
    safe_a = np.where(a_out > 1e-3, a_out / 255.0, 1.0)
    out = np.empty_like(arr)
    out[..., :3] = np.where(a_out > 1e-3, premul[..., :3] / safe_a, 0.0)
    out[..., 3:4] = a_out
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGBA")


def directional_blur_rgb(img: Image.Image, dx: float = 0.0, dy: float = 0.0) -> Image.Image:
    """Fast continuous directional motion blur on an opaque RGB layer (e.g., scrolling phone viewport)."""
    rx = int(round(min(48.0, abs(dx) * 0.40)))
    ry = int(round(min(48.0, abs(dy) * 0.40)))
    if rx < 2 and ry < 2:
        return img
    arr = np.asarray(img, dtype=np.float32)
    if ry >= 2:
        r1 = max(1, ry // 2)
        pad = np.pad(arr, ((r1, r1), (0, 0), (0, 0)), mode="edge")
        k = 2 * r1 + 1
        cs = np.cumsum(pad, axis=0)
        tmp = np.empty_like(arr)
        tmp[0] = cs[k - 1]
        tmp[1:] = cs[k:] - cs[:-k]
        arr = tmp / float(k)
        r2 = max(1, ry - r1)
        pad = np.pad(arr, ((r2, r2), (0, 0), (0, 0)), mode="edge")
        k2 = 2 * r2 + 1
        cs = np.cumsum(pad, axis=0)
        tmp[0] = cs[k2 - 1]
        tmp[1:] = cs[k2:] - cs[:-k2]
        arr = tmp / float(k2)
    if rx >= 2:
        r1 = max(1, rx // 2)
        pad = np.pad(arr, ((0, 0), (r1, r1), (0, 0)), mode="edge")
        k = 2 * r1 + 1
        cs = np.cumsum(pad, axis=1)
        tmp = np.empty_like(arr)
        tmp[:, 0] = cs[:, k - 1]
        tmp[:, 1:] = cs[:, k:] - cs[:, :-k]
        arr = tmp / float(k)
    return Image.fromarray(np.clip(arr + 0.5, 0, 255).astype(np.uint8), "RGB")


def render_shutter_frame(
    render_fn: Callable[[float, Optional[Image.Image]], Image.Image],
    t: float,
    samples: int = 1,
    shutter_angle: float = 200.0,
    bg_fn: Optional[Callable[[float], Image.Image]] = None,
) -> np.ndarray:
    """
    Accumulate N temporal sub-frames across a physical camera shutter window in linear light.
    Reuses a single backdrop render per output frame when bg_fn is provided (4x speedup, identical quality).
    Returns HxWx3 uint8 RGB numpy array ready for ffmpeg pipe.
    """
    bg_once = bg_fn(t) if bg_fn is not None else None
    if samples <= 1:
        return np.asarray(render_fn(t, bg_once).convert("RGB"), dtype=np.uint8)

    half_win = (shutter_angle / 360.0) * (1.0 / FPS) * 0.5
    if samples == 3:
        offsets = (-half_win, 0.0, half_win)
        weights = (0.25, 0.50, 0.25)
    elif samples == 5:
        offsets = (-half_win, -half_win * 0.5, 0.0, half_win * 0.5, half_win)
        weights = (0.12, 0.22, 0.32, 0.22, 0.12)
    else:
        offsets = tuple(np.linspace(-half_win, half_win, 7))
        weights = (0.07, 0.13, 0.19, 0.22, 0.19, 0.13, 0.07)

    acc = np.zeros((H, W, 3), dtype=np.float32)
    for off, w in zip(offsets, weights):
        st = max(0.0, min(DURATION_SEC - 1e-4, t + off))
        bg_copy = bg_once.copy() if bg_once is not None else None
        rgb = np.asarray(render_fn(st, bg_copy).convert("RGB"), dtype=np.uint8)
        acc += _SRGB_TO_LIN[rgb] * float(w)
    idx = np.clip((acc * 4095.0).astype(np.int32), 0, 4095)
    return _LIN_TO_SRGB[idx]


# ---------------------------------------------------------------------------
# Drawing Helpers (100% Borderless, Zero Biscuit Pills)
# ---------------------------------------------------------------------------
def apply_alpha(img: Image.Image, alpha_mult: float) -> Image.Image:
    if alpha_mult >= 0.999:
        return img
    if alpha_mult <= 0.002:
        return Image.new("RGBA", img.size, (0, 0, 0, 0))
    r, g, b, a = img.split()
    a = a.point(lambda p: int(p * alpha_mult))
    return Image.merge("RGBA", (r, g, b, a))


def paste_alpha(canvas: Image.Image, layer: Image.Image, x: int, y: int) -> None:
    """Safely alpha_composite layer onto canvas even when partially out-of-bounds."""
    cw, ch = canvas.size
    lw, lh = layer.size
    if x >= cw or y >= ch or x + lw <= 0 or y + lh <= 0:
        return
    sx0 = max(0, -x)
    sy0 = max(0, -y)
    dx0 = max(0, x)
    dy0 = max(0, y)
    w = min(lw - sx0, cw - dx0)
    h = min(lh - sy0, ch - dy0)
    if w <= 0 or h <= 0:
        return
    if sx0 == 0 and sy0 == 0 and w == lw and h == lh:
        canvas.alpha_composite(layer, (dx0, dy0))
    else:
        sub = layer.crop((sx0, sy0, sx0 + w, sy0 + h))
        canvas.alpha_composite(sub, (dx0, dy0))


def paste_centered_xy(canvas: Image.Image, layer: Image.Image, cx: float, cy: float) -> None:
    paste_alpha(canvas, layer, int(round(cx - layer.width / 2.0)), int(round(cy - layer.height / 2.0)))


def tracked_text_size(fnt: ImageFont.FreeTypeFont, text: str, tracking: float) -> Tuple[float, float]:
    if not text:
        return 0.0, 0.0
    total_w = 0.0
    max_h = 0.0
    for i, ch in enumerate(text):
        bb = fnt.getbbox(ch)
        total_w += fnt.getlength(ch) + (tracking if i < len(text) - 1 else 0.0)
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
        tw, _ = tracked_text_size(fnt, text, tracking)
        x -= tw / 2.0
    cx = x
    for i, ch in enumerate(text):
        draw.text((cx, y), ch, font=fnt, fill=fill)
        cx += fnt.getlength(ch) + (tracking if i < len(text) - 1 else 0.0)


def make_tonal_card(
    w: int,
    h: int,
    radius: int,
    fill_rgba: Tuple[int, int, int, int],
    shadow_alpha: int = 105,
    blur: int = 26,
    dy: int = 14,
    accent_bar_rgb: Optional[Tuple[int, int, int]] = None,
) -> Tuple[Image.Image, int]:
    """
    2x supersampled borderless tonal card with ambient drop shadow (ZERO perimeter outline!).
    Optional subtle interior left accent bar (DESIGN-RULES allowed accent rule).
    """
    pad = blur * 2 + abs(dy) + 12
    cw, ch = w + pad * 2, h + pad * 2

    shad = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shad)
    sd.rounded_rectangle([pad, pad + dy, pad + w, pad + h + dy], radius=radius, fill=(0, 0, 0, shadow_alpha))
    shad = shad.filter(ImageFilter.GaussianBlur(blur))

    ss = 2
    card2x = Image.new("RGBA", (cw * ss, ch * ss), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card2x)
    cd.rounded_rectangle([pad * ss, pad * ss, (pad + w) * ss, (pad + h) * ss], radius=radius * ss, fill=fill_rgba)

    if accent_bar_rgb is not None:
        bw = 6 * ss
        bm = 26 * ss
        cd.rounded_rectangle(
            [pad * ss + 14 * ss, pad * ss + bm, pad * ss + 14 * ss + bw, (pad + h) * ss - bm],
            radius=3 * ss,
            fill=(*accent_bar_rgb, 255),
        )

    card = card2x.resize((cw, ch), Image.Resampling.LANCZOS)
    return Image.alpha_composite(shad, card), pad


def draw_kicker_plain(
    layer: Image.Image,
    y: int,
    text: str,
    accent_rgb: Tuple[int, int, int],
    font_size: int = 24,
    tracking: float = 3.8,
    alpha: float = 1.0,
) -> None:
    """Boss rule #2: NO biscuit pills — wide-tracked plain uppercase typography + crisp accent line/dot."""
    if alpha <= 0.01:
        return
    a = int(round(245 * clamp01(alpha)))
    d = ImageDraw.Draw(layer)
    f = font(FONT_COND_BOLD, font_size)
    tw, th = tracked_text_size(f, text, tracking)
    rule_w = 24
    gap = 16
    total_w = rule_w + gap + tw
    sx = (W - total_w) / 2.0
    cy = y + th * 0.56
    d.rounded_rectangle([sx, cy - 2, sx + rule_w, cy + 2], radius=2, fill=(*accent_rgb, a))
    draw_tracked_text(d, (sx + rule_w + gap, y), text, f, (*accent_rgb, a), tracking=tracking)


def render_serif_line_img(
    segs: List[Tuple[str, bool]],
    size: int,
    accent_rgb: Tuple[int, int, int],
    white_rgb: Tuple[int, int, int],
) -> Image.Image:
    """Pre-render one centered serif headline line onto a tight RGBA strip for masked clip-reveal."""
    f_reg = font(FONT_SERIF_BOLD, size)
    f_it = font(FONT_SERIF_BI, size)
    h = int(size * 1.38)
    img = Image.new("RGBA", (W, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    total_w = 0.0
    parts = []
    for txt, is_em in segs:
        f = f_it if is_em else f_reg
        w = f.getlength(txt)
        parts.append((txt, f, is_em, w))
        total_w += w
    cx = (W - total_w) / 2.0
    y_off = int(size * 0.08)
    for txt, f, is_em, w in parts:
        col = (*accent_rgb, 255) if is_em else (*white_rgb, 255)
        d.text((cx, y_off), txt, font=f, fill=col)
        cx += w
    return img


def composite_masked_line(
    canvas: Image.Image,
    line_img: Image.Image,
    y_dest: int,
    progress: float,
    blur_dy: float = 0.0,
) -> None:
    """
    Studio kinetic typography reveal: glides upward out of an invisible horizontal clip boundary
    with optional directional motion blur during peak velocity!
    """
    p = clamp01(progress)
    if p <= 0.002:
        return
    lh = line_img.height
    e = ease_out_expo(p)
    offset_y = int(round((1.0 - e) * (lh * 0.92)))
    # Clip strictly inside [0 .. lh] slot window
    visible_h = lh - offset_y
    if visible_h <= 1:
        return
    src = line_img
    if abs(blur_dy) >= 4.0:
        src = directional_blur_rgba(src, dy=blur_dy)
    cropped = src.crop((0, 0, W, visible_h))
    alpha = clamp01(p * 3.0)
    if alpha < 0.999:
        cropped = apply_alpha(cropped, alpha)
    paste_alpha(canvas, cropped, 0, y_dest + offset_y)


def draw_star(draw: ImageDraw.ImageDraw, cx: float, cy: float, r_out: float, fill: Tuple[int, ...]) -> None:
    r_in = r_out * 0.44
    pts = []
    for i in range(10):
        ang = -math.pi / 2.0 + i * (math.pi / 5.0)
        r = r_out if i % 2 == 0 else r_in
        pts.append((cx + math.cos(ang) * r, cy + math.sin(ang) * r))
    draw.polygon(pts, fill=fill)


# ---------------------------------------------------------------------------
# Living Volumetric Studio Backdrop (Zero Static Flat Gradients)
# ---------------------------------------------------------------------------
class StudioBackdrop:
    """Precomputes deep editorial gradient + liquid-silk float32 drifting light orbs + deterministic anti-banding grain."""

    def __init__(self, bg_center: str, bg_edge: str, accent_hex: str, seed: int = 1):
        self.accent_arr = np.array(hex_rgb(accent_hex), dtype=np.float32)
        yy, xx = np.mgrid[0:H, 0:W]
        dx = (xx - W * 0.5) / (W * 0.72)
        dy = (yy - H * 0.40) / (H * 0.56)
        dist = np.clip(np.sqrt(dx * dx + dy * dy), 0.0, 1.0) ** 1.28
        c0 = np.array(hex_rgb(bg_center), dtype=np.float32)
        c1 = np.array(hex_rgb(bg_edge), dtype=np.float32)
        base = c0[None, None, :] * (1.0 - dist[..., None]) + c1[None, None, :] * dist[..., None]

        # Ultra-refined faint architectural hairlines (1.4% accent blend)
        grid = ((xx % 90 == 0) | (yy % 90 == 0)).astype(np.float32) * 0.015
        base = base * (1.0 - grid[..., None]) + self.accent_arr[None, None, :] * grid[..., None]

        # Fine deterministic luminance grain added after float glow -> zero H.264 dark-gradient banding
        rng = np.random.default_rng(seed * 97 + 13)
        grain = rng.normal(0.0, 1.35, size=(H, W, 1)).astype(np.float32)
        self.base_arr = (base + grain).astype(np.float32)

        # Low-res float32 field (180x320) upscaled via pure float32 PIL mode="F" (zero 8-bit quantization!)
        self.lw, self.lh = 180, 320
        ly, lx = np.mgrid[0:self.lh, 0:self.lw]
        self.lx = lx.astype(np.float32) / self.lw
        self.ly = ly.astype(np.float32) / self.lh
        self._rgba_buf = np.empty((H, W, 4), dtype=np.uint8)
        self._rgba_buf[..., 3] = 255

    def render(self, t: float, cam_shift_y: float = 0.0) -> Image.Image:
        p1x = 0.50 + 0.22 * math.sin(t * 0.48 + 0.4)
        p1y = 0.25 + 0.07 * math.cos(t * 0.36) + (cam_shift_y * 0.00012)
        p2x = 0.52 - 0.24 * math.cos(t * 0.42 + 1.1)
        p2y = 0.78 + 0.07 * math.sin(t * 0.52) + (cam_shift_y * 0.00015)

        d1 = ((self.lx - p1x) / 0.54) ** 2 + ((self.ly - p1y) / 0.31) ** 2
        d2 = ((self.lx - p2x) / 0.60) ** 2 + ((self.ly - p2y) / 0.33) ** 2
        g_small = (np.exp(-d1 * 2.3) * 0.24 + np.exp(-d2 * 2.1) * 0.15).astype(np.float32)
        g_full = np.asarray(
            Image.fromarray(g_small, mode="F").resize((W, H), Image.Resampling.BILINEAR),
            dtype=np.float32,
        )
        np.clip(
            self.base_arr + g_full[..., None] * self.accent_arr[None, None, :],
            0.0,
            255.0,
            out=self._rgba_buf[..., :3],
            casting="unsafe",
        )
        return Image.fromarray(self._rgba_buf, "RGBA")


# ---------------------------------------------------------------------------
# Generic Dark-Graphite Punch-Hole Android Phone Asset (Entry 13)
# ---------------------------------------------------------------------------
def build_android_shell(screen_w: int, screen_h: int) -> Tuple[Image.Image, Tuple[int, int, int, int], Image.Image, Image.Image]:
    """
    Build sleek generic dark-graphite punch-hole Android hardware shell (Entry 13) +
    screen alpha mask + subtle diagonal glass specular sheen overlay.
    """
    bezel = max(11, int(round(screen_w * 0.032)))
    body_w = screen_w + bezel * 2
    body_h = screen_h + bezel * 2
    outer_r = int(round(body_w * 0.088))
    inner_r = max(18, outer_r - bezel)
    margin = 52

    cw, ch = body_w + margin * 2, body_h + margin * 2

    # Two-stage soft studio drop shadow (deep contact + broad ambient)
    sh1 = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    ImageDraw.Draw(sh1).rounded_rectangle(
        [margin + 4, margin + 22, margin + body_w - 4, margin + body_h + 28],
        radius=outer_r,
        fill=(0, 0, 0, 155),
    )
    sh1 = sh1.filter(ImageFilter.GaussianBlur(26))

    ss = 2
    shell2x = Image.new("RGBA", (cw * ss, ch * ss), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shell2x)
    bx0, by0 = margin * ss, margin * ss
    bx1, by1 = (margin + body_w) * ss, (margin + body_h) * ss

    # Side metallic rockers (volume + power)
    btn_x0 = bx1 - 2
    btn_x1 = bx1 + int(bezel * 0.36 * ss)
    sd.rounded_rectangle([btn_x0, by0 + int(body_h * 0.22 * ss), btn_x1, by0 + int(body_h * 0.34 * ss)], radius=3, fill=(56, 62, 68, 255))
    sd.rounded_rectangle([btn_x0, by0 + int(body_h * 0.38 * ss), btn_x1, by0 + int(body_h * 0.45 * ss)], radius=3, fill=(56, 62, 68, 255))

    # Brushed titanium/graphite rim highlight + matte inner chassis
    sd.rounded_rectangle([bx0, by0, bx1, by1], radius=outer_r * ss, fill=(54, 60, 66, 255))
    sd.rounded_rectangle([bx0 + 4, by0 + 4, bx1 - 4, by1 - 4], radius=outer_r * ss - 3, fill=(20, 23, 26, 255))

    shell = shell2x.resize((cw, ch), Image.Resampling.LANCZOS)
    base = Image.alpha_composite(sh1, shell)

    sx = margin + bezel
    sy = margin + bezel

    mask2x = Image.new("L", (screen_w * ss, screen_h * ss), 0)
    ImageDraw.Draw(mask2x).rounded_rectangle([0, 0, screen_w * ss - 1, screen_h * ss - 1], radius=inner_r * ss, fill=255)
    mask = mask2x.resize((screen_w, screen_h), Image.Resampling.LANCZOS)

    # Diagonal glass specular sheen template (wider than screen so we slide it smoothly across!)
    gw = screen_w * 3
    gh = screen_h
    yy, xx = np.mgrid[0:gh, 0:gw].astype(np.float32)
    diag = (xx - gw * 0.5 + yy * 0.42) / (screen_w * 0.24)
    band = np.exp(-(diag ** 2) * 1.8) * 58.0 + np.exp(-((diag - 0.85) ** 2) * 8.0) * 26.0
    sheen_arr = np.zeros((gh, gw, 4), dtype=np.uint8)
    sheen_arr[..., 0:3] = 255
    sheen_arr[..., 3] = np.clip(band, 0, 75).astype(np.uint8)
    sheen = Image.fromarray(sheen_arr, "RGBA")

    return base, (sx, sy, screen_w, screen_h), mask, sheen


def build_status_bar(screen_w: int, dark_bg: bool) -> Image.Image:
    """Clean Android punch-hole status bar strip keeping headlines below camera dot (Entry 13)."""
    bar_h = max(24, int(round(screen_w * 0.068)))
    ss = 2
    img = Image.new("RGBA", (screen_w * ss, bar_h * ss), (20, 22, 25, 255) if dark_bg else (246, 243, 236, 255))
    d = ImageDraw.Draw(img)
    fg = (234, 234, 232, 255) if dark_bg else (26, 26, 24, 255)
    f = font(FONT_SANS_BOLD, int(bar_h * 0.44 * ss))
    d.text((int(screen_w * 0.065 * ss), int(bar_h * 0.27 * ss)), "9:41", font=f, fill=fg)

    # Punch-hole front camera dot (zero notch, zero Dynamic Island)
    cx = (screen_w * ss) // 2
    cy = (bar_h * ss) // 2
    cam_r = max(7, int(bar_h * 0.25 * ss))
    d.ellipse([cx - cam_r - 2, cy - cam_r - 2, cx + cam_r + 2, cy + cam_r + 2], fill=(42, 46, 50, 255))
    d.ellipse([cx - cam_r, cy - cam_r, cx + cam_r, cy + cam_r], fill=(9, 11, 13, 255))
    d.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=(32, 48, 62, 255))

    # Signal + battery icon (top-right hardware chrome)
    rx = int(screen_w * 0.92 * ss)
    bw, bh = int(bar_h * 0.68 * ss), int(bar_h * 0.34 * ss)
    by0 = cy - bh // 2
    bx0 = rx - bw
    d.rounded_rectangle([bx0, by0, rx, by0 + bh], radius=3, fill=None, outline=fg, width=2)
    d.rectangle([bx0 + 4, by0 + 4, rx - 6, by0 + bh - 4], fill=fg)
    d.rectangle([rx + 1, cy - bh // 4, rx + 4, cy + bh // 4], fill=fg)

    sbx = bx0 - int(bar_h * 0.52 * ss)
    for idx in range(4):
        sh = int((0.14 + idx * 0.06) * bar_h * ss)
        x_b = sbx + idx * int(bar_h * 0.10 * ss)
        d.rectangle([x_b, cy + bh // 2 - sh, x_b + int(bar_h * 0.06 * ss), cy + bh // 2], fill=fg)

    return img.resize((screen_w, bar_h), Image.Resampling.LANCZOS)


class StudioPhoneAsset:
    """High-DPI Android phone mockup with directional scroll blur, specular sweep, and interactive states."""

    def __init__(self, slug: str, dark_status: bool, shots_dir: Path, sw: int, sh: int, meta_entry: dict):
        self.slug = slug
        self.sw = sw
        self.sh = sh
        self.meta = meta_entry
        self.shell_img, self.screen_rect, self.screen_mask, self.sheen_img = build_android_shell(sw, sh)
        self.status_bar = build_status_bar(sw, dark_status)
        self.status_h = self.status_bar.height
        self.viewport_h = sh - self.status_h
        self.css_to_px = float(sw) / 390.0

        full_src = Image.open(shots_dir / f"{slug}_full.png").convert("RGB")
        scaled_h = int(round(full_src.height * (float(sw) / float(full_src.width))))
        self.full_strip = full_src.resize((sw, scaled_h), Image.Resampling.LANCZOS)
        self.max_scroll = max(0, scaled_h - self.viewport_h)

        # Sticky bottom CTA bar
        self.bar_img: Optional[Image.Image] = None
        bar_path = shots_dir / f"{slug}_bar.png"
        if bar_path.exists() and meta_entry.get("barHeightCss", 0) > 0:
            bsrc = Image.open(bar_path).convert("RGBA")
            bh = int(round(bsrc.height * (float(sw) / float(bsrc.width))))
            self.bar_img = bsrc.resize((sw, bh), Image.Resampling.LANCZOS)
        self.hero_bottom_px = int(round(meta_entry.get("heroBottomCss", 640) * self.css_to_px))

        # Optional live interactive booking screens (Linden & Northgate)
        self.states: Dict[str, Image.Image] = {}
        for key in ("book_sum_idle", "book_sum_selected", "book_sum_confirmed"):
            p = shots_dir / f"{slug}_{key}.png"
            if p.exists():
                src = Image.open(p).convert("RGB")
                self.states[key] = src.resize((sw, self.viewport_h), Image.Resampling.LANCZOS)

    def css_offset(self, selector: str, fallback: int = 0, top_margin_css: int = 18) -> int:
        val = self.meta.get("offsets", {}).get(selector, fallback) - top_margin_css
        return min(self.max_scroll, max(0, int(round(val * self.css_to_px))))

    def render(
        self,
        scroll_px: float = 0.0,
        scroll_vel_px: float = 0.0,
        state_img: Optional[Image.Image] = None,
        state_blend_from: Optional[Image.Image] = None,
        state_blend_t: float = 1.0,
        sheen_pos: Optional[float] = None,
        touch_pt: Optional[Tuple[float, float, float]] = None,  # (norm_x, norm_y, press_0_1)
        ripple: Optional[Tuple[float, float, float]] = None,    # (norm_x, norm_y, age_0_1)
        accent_rgb: Tuple[int, int, int] = (255, 255, 255),
        show_bar_force: Optional[bool] = None,
    ) -> Image.Image:
        vp = Image.new("RGBA", (self.sw, self.sh), (244, 241, 235, 255))

        if state_img is not None:
            if state_blend_from is not None and state_blend_t < 0.999:
                cur_rgb = Image.blend(state_blend_from, state_img, clamp01(state_blend_t))
            else:
                cur_rgb = state_img
            if abs(scroll_vel_px) >= 8.0:
                cur_rgb = directional_blur_rgb(cur_rgb, dy=scroll_vel_px * 0.65)
            vp.paste(cur_rgb.convert("RGBA"), (0, self.status_h))
        else:
            y = int(round(max(0.0, min(float(self.max_scroll), scroll_px))))
            slice_rgb = self.full_strip.crop((0, y, self.sw, min(self.full_strip.height, y + self.viewport_h)))
            if abs(scroll_vel_px) >= 12.0:
                slice_rgb = directional_blur_rgb(slice_rgb, dy=scroll_vel_px * 0.55)
            vp.paste(slice_rgb.convert("RGBA"), (0, self.status_h))

            if self.bar_img is not None:
                if show_bar_force is not None:
                    show_bar = show_bar_force
                else:
                    show_bar = (self.slug == "saffron-and-salt") or (y + self.viewport_h * 0.45 >= self.hero_bottom_px)
                if show_bar:
                    vp.alpha_composite(self.bar_img, (0, self.sh - self.bar_img.height))

        # Status bar cleanly on top of viewport
        vp.paste(self.status_bar, (0, 0))

        # Expanding tap ripple ring inside viewport
        if ripple is not None:
            rx_n, ry_n, age = ripple
            if 0.0 < age < 1.0:
                rx = int(round(rx_n * self.sw))
                ry = int(round(self.status_h + ry_n * self.viewport_h))
                rad = int(round(lerp(10, 68, ease_out_expo(age))))
                a_ring = int(round(215 * (1.0 - age) ** 1.4))
                a_fill = int(round(70 * (1.0 - age) ** 1.6))
                ov = Image.new("RGBA", (self.sw, self.sh), (0, 0, 0, 0))
                od = ImageDraw.Draw(ov)
                od.ellipse([rx - rad, ry - rad, rx + rad, ry + rad], fill=(*accent_rgb, a_fill))
                od.ellipse([rx - rad, ry - rad, rx + rad, ry + rad], outline=(*accent_rgb, a_ring), width=4)
                vp.alpha_composite(ov)

        # Frosted touch cursor dot
        if touch_pt is not None:
            tx_n, ty_n, press = touch_pt
            tx = int(round(tx_n * self.sw))
            ty = int(round(self.status_h + ty_n * self.viewport_h))
            rad = int(round(lerp(24, 17, clamp01(press))))
            ov = Image.new("RGBA", (self.sw, self.sh), (0, 0, 0, 0))
            od = ImageDraw.Draw(ov)
            od.ellipse([tx - rad - 5, ty - rad - 5, tx + rad + 5, ty + rad + 5], fill=(0, 0, 0, 48))
            od.ellipse([tx - rad, ty - rad, tx + rad, ty + rad], fill=(255, 255, 255, 195))
            od.ellipse([tx - rad + 5, ty - rad + 5, tx + rad - 5, ty + rad - 5], fill=(*accent_rgb, 145))
            vp.alpha_composite(ov)

        # Diagonal specular glass reflection sweep
        if sheen_pos is not None and -0.4 <= sheen_pos <= 1.4:
            sx_crop = int(round(lerp(self.sw * 2, 0, clamp01(sheen_pos))))
            sx_crop = max(0, min(self.sheen_img.width - self.sw, sx_crop))
            sheen_slice = self.sheen_img.crop((sx_crop, 0, sx_crop + self.sw, self.sh))
            vp.alpha_composite(sheen_slice)

        out = self.shell_img.copy()
        sx, sy, _, _ = self.screen_rect
        out.paste(vp, (sx, sy), self.screen_mask)
        return out


# ---------------------------------------------------------------------------
# Studio Audio Engine (Warm Rhodes Chords + Synced Whip-Whooshes + UI Taps)
# ---------------------------------------------------------------------------
def synthesize_studio_audio(
    wav_path: Path,
    chord_freqs: List[List[float]],
    whoosh_times: List[float],
    tap_times: List[float],
    seed: int = 1,
) -> None:
    sr = 44100
    n = int(sr * DURATION_SEC)
    t = np.linspace(0.0, DURATION_SEC, n, endpoint=False, dtype=np.float64)
    left = np.zeros(n, dtype=np.float64)
    right = np.zeros(n, dtype=np.float64)

    # Warm stereo Rhodes / felt-piano chords (4 bars across 15s)
    bar_len = DURATION_SEC / len(chord_freqs)
    for idx, freqs in enumerate(chord_freqs):
        t0 = idx * bar_len
        t1 = min(DURATION_SEC, (idx + 1) * bar_len + 0.35)
        i0, i1 = int(t0 * sr), min(n, int(t1 * sr))
        lt = t[i0:i1] - t0
        env = (1.0 - np.exp(-lt / 0.045)) * np.exp(-lt / (bar_len * 0.92))
        chord_l = np.zeros(i1 - i0, dtype=np.float64)
        chord_r = np.zeros(i1 - i0, dtype=np.float64)
        for j, f in enumerate(freqs):
            # Soft Rhodes bell overtone + warm fundamental + gentle stereo spread
            pan = 0.38 + 0.24 * (j / max(1, len(freqs) - 1))
            sig = (
                0.70 * np.sin(2.0 * np.pi * f * lt)
                + 0.20 * np.sin(2.0 * np.pi * (f * 2.0) * lt) * np.exp(-lt * 2.8)
                + 0.07 * np.sin(2.0 * np.pi * (f * 3.0) * lt) * np.exp(-lt * 5.2)
            )
            chord_l += sig * (1.0 - pan)
            chord_r += sig * pan
        # Sub-bass anchor on root octave below
        sub = 0.28 * np.sin(2.0 * np.pi * (freqs[0] * 0.5) * lt) * (1.0 - np.exp(-lt / 0.08)) * np.exp(-lt / (bar_len * 1.1))
        left[i0:i1] += (chord_l / len(freqs)) * env * 0.22 + sub * 0.14
        right[i0:i1] += (chord_r / len(freqs)) * env * 0.22 + sub * 0.14

    # Soft rhythmic brushed pulse (subtle editorial forward momentum)
    beat_period = 0.625  # 96 BPM
    rng = np.random.default_rng(seed * 313 + 7)
    for k in range(int(DURATION_SEC / beat_period)):
        bt = k * beat_period + 0.12
        i0 = int(bt * sr)
        dur_s = int(0.06 * sr)
        if i0 + dur_s >= n:
            break
        lt = np.linspace(0.0, 0.06, dur_s, endpoint=False)
        if k % 2 == 0:
            # Soft warm muted kick
            freq_sw = 92.0 * np.exp(-lt * 34.0) + 46.0
            kick = np.sin(2.0 * np.pi * np.cumsum(freq_sw) / sr) * np.exp(-lt * 42.0) * 0.055
            left[i0:i0 + dur_s] += kick
            right[i0:i0 + dur_s] += kick
        else:
            # Airy studio shaker tick
            sh = rng.normal(0.0, 1.0, dur_s) * np.exp(-lt * 95.0) * 0.012
            left[i0:i0 + dur_s] += sh * 0.8
            right[i0:i0 + dur_s] += sh * 1.1

    # Synced cinematic whip-pan whooshes (smooth filtered noise rise/fall)
    for wt in whoosh_times:
        dur = 0.26
        i0 = max(0, int((wt - dur * 0.45) * sr))
        i1 = min(n, int((wt + dur * 0.55) * sr))
        m = i1 - i0
        if m < 64:
            continue
        noise = rng.normal(0.0, 1.0, m)
        # Smooth low-pass moving average for silky cinema air swoosh
        win = 28
        smooth = np.convolve(noise, np.ones(win) / win, mode="same")
        smooth = np.convolve(smooth, np.ones(18) / 18.0, mode="same")
        lt = np.linspace(0.0, 1.0, m)
        env = np.sin(np.pi * lt) ** 1.6
        # Gentle stereo sweep left->right
        sw_l = smooth * env * (0.28 * (1.0 - 0.3 * lt))
        sw_r = smooth * env * (0.28 * (0.7 + 0.3 * lt))
        left[i0:i1] += sw_l
        right[i0:i1] += sw_r

    # Synced tactile UI tap chimes (crisp soft glass/woodblock click)
    for tt in tap_times:
        dur = 0.09
        i0 = max(0, int(tt * sr))
        i1 = min(n, int((tt + dur) * sr))
        m = i1 - i0
        if m < 32:
            continue
        lt = np.linspace(0.0, dur, m, endpoint=False)
        tap = (
            0.14 * np.sin(2.0 * np.pi * (920.0 * np.exp(-lt * 14.0) + 520.0) * lt) * np.exp(-lt * 48.0)
            + 0.06 * np.sin(2.0 * np.pi * 1560.0 * lt) * np.exp(-lt * 75.0)
        )
        left[i0:i1] += tap
        right[i0:i1] += tap

    # Master fade in/out + target RMS normalization (-22 dB, zero clipping)
    fade_in = int(0.18 * sr)
    fade_out = int(0.55 * sr)
    left[:fade_in] *= np.linspace(0.0, 1.0, fade_in)
    right[:fade_in] *= np.linspace(0.0, 1.0, fade_in)
    left[-fade_out:] *= np.linspace(1.0, 0.0, fade_out)
    right[-fade_out:] *= np.linspace(1.0, 0.0, fade_out)

    stereo = np.stack([left, right], axis=1)
    rms = float(np.sqrt(np.mean(stereo ** 2)) + 1e-9)
    target_rms = 10.0 ** (-22.0 / 20.0)
    stereo = np.tanh(stereo * (target_rms / rms) * 1.15) * 0.85
    pcm = np.clip(stereo * 32767.0, -32767, 32767).astype(np.int16)

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


# ---------------------------------------------------------------------------
# Beat 1 Bespoke Visual Cards (Zero Perimeter Borders!)
# ---------------------------------------------------------------------------
def build_beat1_visual_pdf_card(accent_rgb: Tuple[int, int, int], card_fill: Tuple[int, int, int, int]) -> Image.Image:
    """Reel 08: Simulated tiny blurry pinch-zoom PDF menu card getting flagged."""
    cw, ch = 820, 470
    card, pad = make_tonal_card(cw, ch, 30, card_fill, shadow_alpha=125, blur=28, dy=16)
    d = ImageDraw.Draw(card)
    x0, y0 = pad, pad

    # Header bar inside tonal card (pure tonal fill, zero border)
    d.rounded_rectangle([x0 + 28, y0 + 28, x0 + cw - 28, y0 + 96], radius=16, fill=(255, 255, 255, 18))
    d.text((x0 + 54, y0 + 48), "menu_final_v3_scan.pdf  (6.8 MB)", font=font(FONT_SANS_MED, 24), fill=(215, 210, 204, 220))

    # Simulated tiny unreadable zoomed-out PDF scan sheet
    pdf_box = Image.new("RGBA", (620, 260), (244, 238, 228, 255))
    pd = ImageDraw.Draw(pdf_box)
    f_tiny = font(FONT_SANS_REG, 11)
    pd.text((22, 16), "HOUSE DRINKS & BAKERY MENU", font=font(FONT_SERIF_BOLD, 15), fill=(40, 35, 30, 255))
    for row in range(9):
        yy = 48 + row * 21
        pd.text((22, yy), f"Espresso / Cortado / Oat Latte ............ $4.50", font=f_tiny, fill=(75, 70, 64, 255))
        pd.text((330, yy), f"Cardamom Bun / Scone .......... $5.00", font=f_tiny, fill=(75, 70, 64, 255))
    # Slightly blurry like an unoptimized phone PDF pinch-zoom
    pdf_blur = pdf_box.filter(ImageFilter.GaussianBlur(1.7))
    card.paste(pdf_blur, (x0 + 100, y0 + 118))

    # Tonal red/amber friction pill at bottom (borderless!)
    d.rounded_rectangle([x0 + 190, y0 + 394, x0 + cw - 190, y0 + 446], radius=26, fill=(*accent_rgb, 240))
    draw_tracked_text(d, (x0 + cw / 2, y0 + 408), "PINCH.  ZOOM.  LEAVE.", font(FONT_COND_BOLD, 24), (18, 14, 10, 255), tracking=2.8, anchor_center_x=True)
    return card


def build_beat1_dm_bubble(text: str, time_str: str, accent_rgb: Tuple[int, int, int], card_fill: Tuple[int, int, int, int]) -> Image.Image:
    """Reel 09: Borderless dark-glass DM notification card."""
    cw, ch = 820, 128
    card, pad = make_tonal_card(cw, ch, 26, card_fill, shadow_alpha=110, blur=22, dy=12, accent_bar_rgb=accent_rgb)
    d = ImageDraw.Draw(card)
    x0, y0 = pad, pad
    # Avatar circle (borderless tonal fill)
    d.ellipse([x0 + 42, y0 + 34, x0 + 102, y0 + 94], fill=(*accent_rgb, 56))
    d.text((x0 + 62, y0 + 48), "DM", font=font(FONT_COND_BOLD, 24), fill=(*accent_rgb, 255))
    d.text((x0 + 126, y0 + 34), text, font=font(FONT_SANS_BOLD, 30), fill=(246, 244, 240, 255))
    d.text((x0 + 126, y0 + 78), f"Instagram DM  ·  {time_str}", font=font(FONT_SANS_REG, 22), fill=(185, 195, 188, 220))
    return card


def build_beat1_maps_card(accent_rgb: Tuple[int, int, int], card_fill: Tuple[int, int, int, int]) -> Image.Image:
    """Reel 10: Borderless Google Maps card with 4.9 stars and glaring empty 'Add website' gap."""
    cw, ch = 840, 440
    card, pad = make_tonal_card(cw, ch, 30, card_fill, shadow_alpha=125, blur=28, dy=16)
    d = ImageDraw.Draw(card)
    x0, y0 = pad, pad
    d.text((x0 + 48, y0 + 42), "Local Barbershop", font=font(FONT_SANS_BOLD, 42), fill=(246, 244, 240, 255))
    # 5 crisp gold stars
    d.text((x0 + 48, y0 + 104), "4.9", font=font(FONT_SANS_BOLD, 30), fill=(*accent_rgb, 255))
    for i in range(5):
        draw_star(d, x0 + 122 + i * 32, y0 + 121, 13, (*accent_rgb, 255))
    d.text((x0 + 286, y0 + 106), "(240 reviews)  ·  Open", font=font(FONT_SANS_REG, 26), fill=(188, 186, 180, 230))

    # Action tonal chips row (Directions / Call / missing Website)
    chip_y = y0 + 178
    for idx, (lbl, highlight) in enumerate([("Directions", False), ("Call", False), ("No Website", True)]):
        bx = x0 + 48 + idx * 252
        fill = (*accent_rgb, 235) if highlight else (255, 255, 255, 24)
        txt_col = (18, 16, 14, 255) if highlight else (232, 230, 225, 235)
        d.rounded_rectangle([bx, chip_y, bx + 232, chip_y + 64], radius=32, fill=fill)
        draw_tracked_text(d, (bx + 116, chip_y + 19), lbl.upper(), font(FONT_COND_BOLD, 24), txt_col, tracking=1.8, anchor_center_x=True)

    # Stark blank website row
    d.rounded_rectangle([x0 + 48, y0 + 280, x0 + cw - 48, y0 + 382], radius=20, fill=(255, 255, 255, 16))
    d.text((x0 + 78, y0 + 302), "WEBSITE", font=font(FONT_COND_BOLD, 20), fill=(*accent_rgb, 230))
    d.text((x0 + 78, y0 + 332), "Add website  —  customers click away", font=font(FONT_SANS_MED, 26), fill=(242, 236, 226, 235))
    return card


def build_beat1_fragment_tile(title: str, sub: str, accent_rgb: Tuple[int, int, int], card_fill: Tuple[int, int, int, int]) -> Image.Image:
    """Reel 11: Borderless scattered link tile."""
    cw, ch = 720, 122
    card, pad = make_tonal_card(cw, ch, 26, card_fill, shadow_alpha=110, blur=22, dy=12, accent_bar_rgb=accent_rgb)
    d = ImageDraw.Draw(card)
    x0, y0 = pad, pad
    d.text((x0 + 48, y0 + 24), title, font=font(FONT_SANS_BOLD, 32), fill=(248, 244, 238, 255))
    d.text((x0 + 48, y0 + 68), sub, font=font(FONT_SANS_REG, 24), fill=(196, 186, 174, 230))
    return card


def build_beat1_reviews_card(accent_rgb: Tuple[int, int, int], card_fill: Tuple[int, int, int, int]) -> Image.Image:
    """Reel 12: Established shop 4.8 stars & 400+ reviews card."""
    cw, ch = 820, 360
    card, pad = make_tonal_card(cw, ch, 30, card_fill, shadow_alpha=125, blur=28, dy=16)
    d = ImageDraw.Draw(card)
    x0, y0 = pad, pad
    for i in range(5):
        draw_star(d, x0 + cw / 2 - 104 + i * 52, y0 + 72, 20, (*accent_rgb, 255))
    draw_tracked_text(d, (x0 + cw / 2, y0 + 122), "4.8  ·  400+ LOCAL REVIEWS", font(FONT_SANS_BLACK, 38), (248, 242, 234, 255), tracking=1.2, anchor_center_x=True)
    d.rounded_rectangle([x0 + 120, y0 + 206, x0 + cw - 120, y0 + 298], radius=22, fill=(255, 255, 255, 18))
    draw_tracked_text(d, (x0 + cw / 2, y0 + 236), "Still sending customers to Facebook?", font(FONT_SANS_MED, 28), (*accent_rgb, 255), tracking=0.4, anchor_center_x=True)
    return card


def build_insight_card(num: str, title: str, sub: str, accent_rgb: Tuple[int, int, int], card_fill: Tuple[int, int, int, int]) -> Image.Image:
    """Beat 2 sleek borderless studio feature card with numbered tonal badge."""
    cw, ch = 876, 168
    card, pad = make_tonal_card(cw, ch, 28, card_fill, shadow_alpha=115, blur=24, dy=14)
    d = ImageDraw.Draw(card)
    x0, y0 = pad, pad
    # Numbered tonal circle (zero border!)
    d.ellipse([x0 + 36, y0 + 40, x0 + 124, y0 + 128], fill=(*accent_rgb, 42))
    draw_tracked_text(d, (x0 + 80, y0 + 66), num, font(FONT_SANS_BLACK, 32), (*accent_rgb, 255), tracking=1.0, anchor_center_x=True)
    d.text((x0 + 154, y0 + 40), title, font=font(FONT_SANS_BOLD, 34), fill=(248, 246, 242, 255))
    d.text((x0 + 154, y0 + 92), sub, font=font(FONT_SANS_REG, 25), fill=(198, 200, 196, 232))
    return card


def build_floating_callout(text: str, accent_rgb: Tuple[int, int, int], dark_fill: Tuple[int, int, int, int]) -> Image.Image:
    """Beat 3 sleek borderless pill callout floating cleanly below the Android phone."""
    f = font(FONT_COND_BOLD, 27)
    tw, _ = tracked_text_size(f, text.upper(), 2.4)
    cw = int(tw + 96)
    ch = 68
    card, pad = make_tonal_card(cw, ch, 34, dark_fill, shadow_alpha=95, blur=18, dy=10)
    d = ImageDraw.Draw(card)
    x0, y0 = pad, pad
    # Glowing accent dot
    d.ellipse([x0 + 28, y0 + ch // 2 - 7, x0 + 42, y0 + ch // 2 + 7], fill=(*accent_rgb, 255))
    draw_tracked_text(d, (x0 + 58, y0 + 19), text.upper(), f, (246, 244, 240, 255), tracking=2.4)
    return card


def build_cover_endcard(
    backdrop: StudioBackdrop,
    kicker: str,
    title_lines: List[List[Tuple[str, bool]]],
    price_line: str,
    cta_keyword: str,
    handle_line: str,
    accent_rgb: Tuple[int, int, int],
    card_fill: Tuple[int, int, int, int],
    preview_phone: Optional[Image.Image] = None,
    preview_prebuilt: bool = False,
) -> Image.Image:
    """
    Build iconic, ultra-legible 3:4 IG profile-grid safe-zone End Card & Cover PNG (y=260..1640).
    ZERO perimeter borders/outlines; ZERO headline biscuit pills.
    """
    canvas = backdrop.render(14.5)
    d = ImageDraw.Draw(canvas)

    # All primary content cleanly centered inside Instagram 3:4 profile grid crop [y=240..1680]
    if preview_phone is not None:
        if preview_prebuilt:
            mini = preview_phone
        else:
            mini = preview_phone.resize((int(preview_phone.width * 0.44), int(preview_phone.height * 0.44)), Image.Resampling.LANCZOS)
        paste_centered_xy(canvas, mini, W / 2.0, 520)
        y_kicker = 855
    else:
        y_kicker = 460

    draw_kicker_plain(canvas, y_kicker, kicker, accent_rgb, font_size=24, tracking=4.0)

    cy = y_kicker + 56
    for segs in title_lines:
        limg = render_serif_line_img(segs, 74 if preview_phone is None else 66, accent_rgb, (248, 246, 242))
        paste_alpha(canvas, limg, 0, cy)
        cy += (84 if preview_phone is None else 76)

    # Clean pricing subline
    f_sub = font(FONT_SANS_MED, 31)
    draw_tracked_text(d, (W / 2.0, cy + 26), price_line, f_sub, (216, 214, 208, 242), tracking=0.4, anchor_center_x=True)

    # Strong borderless CTA pill (solid accent fill + deep shadow)
    cta_text = f'COMMENT "{cta_keyword}" FOR A FREE MOCKUP'
    f_cta = font(FONT_COND_BOLD, 30)
    tw, _ = tracked_text_size(f_cta, cta_text, 2.2)
    pw = int(max(680, tw + 96))
    ph = 94
    pill, ppad = make_tonal_card(pw, ph, 47, (*accent_rgb, 255), shadow_alpha=125, blur=24, dy=12)
    pd = ImageDraw.Draw(pill)
    draw_tracked_text(pd, (ppad + pw / 2.0, ppad + 30), cta_text, f_cta, (16, 15, 14, 255), tracking=2.2, anchor_center_x=True)
    paste_centered_xy(canvas, pill, W / 2.0, cy + 148)

    # Clean brand handle + URL
    draw_tracked_text(
        d,
        (W / 2.0, cy + 236),
        handle_line,
        font(FONT_SANS_BOLD, 29),
        (242, 240, 236, 242),
        tracking=1.0,
        anchor_center_x=True,
    )

    # Minimal subtle disclaimer well inside 3:4 bottom safe edge
    draw_tracked_text(
        d,
        (W / 2.0, 1612),
        "Fictional demo design  ·  No obligation preview",
        font(FONT_SANS_REG, 22),
        (168, 168, 164, 200),
        tracking=0.6,
        anchor_center_x=True,
    )
    return canvas


def draw_progress_hairline(canvas: Image.Image, progress: float, accent_rgb: Tuple[int, int, int]) -> None:
    d = ImageDraw.Draw(canvas)
    w = int(round(W * clamp01(progress)))
    if w > 0:
        d.rectangle([0, H - 5, w, H], fill=(*accent_rgb, 230))


# ---------------------------------------------------------------------------
# Reel Configurations (Reels 08–13: 6 Brand-New Daily Reels for Nov 19–24)
# ---------------------------------------------------------------------------
REEL_SPECS = [
    {
        "id": "08",
        "filename": "eva-reel-08-five-second-menu-test",
        "slug": "harbor-street-coffee",
        "dark_status": False,
        "bg_center": "#1f1712",
        "bg_edge": "#0c0907",
        "accent": "#e39c52",
        "card_fill": (38, 30, 24, 235),
        "seed": 8,
        "b1_kind": "pdf",
        "b1_kicker": "THE 5-SECOND PHONE TEST",
        "b1_lines": [
            [("If customers have to ", False)],
            [("pinch-zoom", True), (" your menu,", False)],
            [("they leave.", False)],
        ],
        "b2_kicker": "ONE FAST PAGE",
        "b2_lines": [
            [("Readable in ", False), ("sunlight.", True)],
            [("Ready in ", False), ("one tap.", True)],
        ],
        "b2_cards": [
            ("01", "Crisp mobile menu", "Real text, live prices — zero PDF downloads"),
            ("02", "Daily special up front", "Morning bakes & rotating filter highlighted"),
            ("03", "Hours & Maps pinned", "One tap straight to your door"),
        ],
        "b3_kicker": "LIVE MOBILE DEMO  ·  CAFES",
        "b3_callouts": [
            (0.0, 2.0, "Instant hero + today's pour"),
            (2.0, 4.2, "Clean prices — zero pinch-zoom"),
            (4.2, 6.2, "Live hours & 1-tap directions"),
        ],
        "b4_kicker": "FREE PREVIEW BEFORE YOU PAY",
        "b4_lines": [
            [("See your ", False), ("cafe", True)],
            [("live on a phone.", False)],
        ],
        "b4_price": "Fixed from $50  ·  Zero monthly lock-in",
        "cta_keyword": "MENU",
        "chords": [
            [220.00, 277.18, 329.63, 415.30],  # A maj7
            [185.00, 220.00, 277.18, 329.63],  # F#m7
            [146.83, 220.00, 277.18, 369.99],  # D maj9
            [164.81, 246.94, 293.66, 369.99],  # E9sus4
        ],
        "interactive": False,
    },
    {
        "id": "09",
        "filename": "eva-reel-09-salon-interactive-booking",
        "slug": "linden-and-stone",
        "dark_status": False,
        "bg_center": "#14221c",
        "bg_edge": "#09100d",
        "accent": "#e38c6d",
        "card_fill": (28, 44, 37, 236),
        "seed": 9,
        "b1_kind": "dms",
        "b1_kicker": "11:42 PM IN YOUR DMs",
        "b1_lines": [
            [("Answering the ", False), ("same", True)],
            [("3 price DMs", True), (" every night?", False)],
        ],
        "b1_dms": [
            ("How much is builder gel?", "11:38 PM"),
            ("Any Friday slots with Sofia?", "11:41 PM"),
            ("Where is your booking link?", "11:42 PM"),
        ],
        "b2_kicker": "LET YOUR PAGE ANSWER",
        "b2_lines": [
            [("Clear menu. ", False), ("Tap a slot.", True)],
            [("Zero midnight DMs.", False)],
        ],
        "b2_cards": [
            ("01", "Filterable service menu", "Hair, colour & nail prices clear up front"),
            ("02", "Live slot picker", "Clients pick service, stylist & open time"),
            ("03", "Links to your booker", "Vagaro, Fresha, GlossGenius or Square"),
        ],
        "b3_kicker": "LIVE INTERACTIVE DEMO  ·  SALONS",
        "b3_callouts": [
            (0.0, 2.2, "Editorial salon hero & menu"),
            (2.2, 4.1, "Tap time slot -> $60 live total"),
            (4.1, 6.2, "Instant slot request confirmed"),
        ],
        "b4_kicker": "FREE PREVIEW BEFORE YOU PAY",
        "b4_lines": [
            [("Stop answering ", False), ("price", True)],
            [("DMs at midnight.", False)],
        ],
        "b4_price": "Fixed from $50  ·  Live in 2-3 days",
        "cta_keyword": "SALON",
        "chords": [
            [196.00, 246.94, 293.66, 369.99],  # G maj7
            [164.81, 246.94, 293.66, 392.00],  # Em9
            [130.81, 196.00, 246.94, 329.63],  # C maj7
            [146.83, 220.00, 261.63, 329.63],  # D9sus4
        ],
        "interactive": True,
        "tap_time_xy": (0.5000, 0.4462),
        "tap_confirm_xy": (0.5000, 0.7288),
    },
    {
        "id": "10",
        "filename": "eva-reel-10-barber-walkin-conversion",
        "slug": "northgate-barber-room",
        "dark_status": True,
        "bg_center": "#181b20",
        "bg_edge": "#0a0b0d",
        "accent": "#e0b35c",
        "card_fill": (34, 38, 44, 238),
        "seed": 10,
        "b1_kind": "maps",
        "b1_kicker": "THE GOOGLE MAPS LEAK",
        "b1_lines": [
            [("5-star barbershop.", False)],
            [("Dead-end ", False), ("website click.", True)],
        ],
        "b2_kicker": "TURN SEARCHES INTO CHAIRS",
        "b2_lines": [
            [("Prices. Barbers.", False)],
            [("Booked in ", False), ("30 seconds.", True)],
        ],
        "b2_cards": [
            ("01", "Live open & walk-in status", "Shows closing time & walk-in cutoff"),
            ("02", "Tap-to-book cuts & fades", "Fade + beard combo with live GBP total"),
            ("03", "Connects to your chairs", "Fresha, Booksy, Square or WhatsApp"),
        ],
        "b3_kicker": "LIVE INTERACTIVE DEMO  ·  BARBERS",
        "b3_callouts": [
            (0.0, 2.2, "Bold brand + live open status"),
            (2.2, 4.1, "Tap 10:00 -> Fade + beard £30"),
            (4.1, 6.2, "Booking request confirmed"),
        ],
        "b4_kicker": "FREE PREVIEW BEFORE YOU PAY",
        "b4_lines": [
            [("Turn Maps clicks", False)],
            [("into ", False), ("booked chairs.", True)],
        ],
        "b4_price": "Fixed from $50  ·  No monthly lock-in",
        "cta_keyword": "CUT",
        "chords": [
            [174.61, 220.00, 261.63, 329.63],  # F maj7
            [146.83, 220.00, 261.63, 349.23],  # Dm9
            [196.00, 233.08, 293.66, 349.23],  # Gm7
            [130.81, 196.00, 233.08, 293.66],  # C9
        ],
        "interactive": True,
        "tap_time_xy": (0.6038, 0.2972),
        "tap_confirm_xy": (0.5000, 0.7751),
    },
    {
        "id": "11",
        "filename": "eva-reel-11-grill-whatsapp-orders",
        "slug": "saffron-and-salt",
        "dark_status": True,
        "bg_center": "#211510",
        "bg_edge": "#0c0806",
        "accent": "#eba33c",
        "card_fill": (42, 30, 24, 238),
        "seed": 11,
        "b1_kind": "fragment",
        "b1_kicker": "DINNER RUSH FRICTION",
        "b1_lines": [
            [("3 scattered links", True)],
            [("just to order dinner?", False)],
        ],
        "b1_tiles": [
            ("Instagram Bio PDF", "Slow download · tiny prices"),
            ("WhatsApp Number", "Copy-paste just to ask what's open"),
            ("Google Maps Pin", "Zero menu · zero direct order button"),
        ],
        "b2_kicker": "ONE FAST PAGE  ·  ZERO FRICTION",
        "b2_lines": [
            [("Crave. Scroll.", False)],
            [("Order on ", False), ("WhatsApp.", True)],
        ],
        "b2_cards": [
            ("01", "Category jump rail", "Starters, Grill & Bread in one thumb tap"),
            ("02", "Moody food presentation", "Crisp dish descriptions & clear pricing"),
            ("03", "Sticky 1-tap order bar", "WhatsApp & Call pinned as they scroll"),
        ],
        "b3_kicker": "LIVE MOBILE DEMO  ·  GRILLS",
        "b3_callouts": [
            (0.0, 2.0, "Atmospheric hero + category rail"),
            (2.0, 4.2, "Scannable grill menu & platters"),
            (4.2, 6.2, "Sticky Order on WhatsApp bar"),
        ],
        "b4_kicker": "FREE PREVIEW BEFORE YOU PAY",
        "b4_lines": [
            [("One tap from ", False), ("menu", True)],
            [("to WhatsApp order.", False)],
        ],
        "b4_price": "Fixed from $50  ·  Ready in 2-3 days",
        "cta_keyword": "MENU",
        "chords": [
            [164.81, 196.00, 246.94, 329.63],  # Em7
            [146.83, 196.00, 220.00, 293.66],  # Dsus4
            [130.81, 196.00, 246.94, 293.66],  # C maj9
            [123.47, 185.00, 220.00, 293.66],  # Bm7
        ],
        "interactive": False,
    },
    {
        "id": "12",
        "filename": "eva-reel-12-established-shop-upgrade",
        "slug": "the-copper-kettle",
        "dark_status": False,
        "bg_center": "#231914",
        "bg_edge": "#0e0a08",
        "accent": "#e08452",
        "card_fill": (44, 34, 28, 236),
        "seed": 12,
        "b1_kind": "reviews",
        "b1_kicker": "ESTABLISHED  ·  LOVED  ·  NO SITE",
        "b1_lines": [
            [("Years of ", False), ("5-star regulars.", True)],
            [("Still no real website?", False)],
        ],
        "b2_kicker": "KEEP YOUR SOUL  ·  UPGRADE THE CLICK",
        "b2_lines": [
            [("Warm brand feel.", False)],
            [("Built ", False), ("in 48 hours.", True)],
        ],
        "b2_cards": [
            ("01", "Custom to your real vibe", "Typography & warmth — zero cookie-cutter"),
            ("02", "All-day menu & specials", "Readable dotted-leader menu on any phone"),
            ("03", "One fixed price", "Zero monthly agency retainers"),
        ],
        "b3_kicker": "LIVE MOBILE DEMO  ·  LOCAL SHOPS",
        "b3_callouts": [
            (0.0, 2.0, "Warm editorial brand hero"),
            (2.0, 4.2, "Clean brunch & bakery menu"),
            (4.2, 6.2, "Hours, map & direct call"),
        ],
        "b4_kicker": "FREE PREVIEW BEFORE YOU PAY",
        "b4_lines": [
            [("Give your ", False), ("reputation", True)],
            [("a real home.", False)],
        ],
        "b4_price": "Fixed from $50  ·  Zero agency fees",
        "cta_keyword": "SITE",
        "chords": [
            [174.61, 220.00, 261.63, 349.23],  # F maj
            [130.81, 196.00, 246.94, 329.63],  # C maj7
            [146.83, 220.00, 261.63, 329.63],  # Dm7
            [196.00, 246.94, 293.66, 349.23],  # G7sus
        ],
        "interactive": False,
    },
]


# ---------------------------------------------------------------------------
# Standard Single-Vertical Studio Reel Renderer (Reels 08–12)
# ---------------------------------------------------------------------------
def render_vertical_reel(cfg: dict, shots_dir: Path, meta: dict, out_dir: Path) -> Tuple[Path, Path]:
    t_start = time.time()
    rid = cfg["id"]
    fname = cfg["filename"]
    accent_rgb = hex_rgb(cfg["accent"])
    card_fill = cfg["card_fill"]
    white_rgb = (248, 246, 242)

    backdrop = StudioBackdrop(cfg["bg_center"], cfg["bg_edge"], cfg["accent"], seed=cfg["seed"])
    slug = cfg["slug"]
    phone = StudioPhoneAsset(slug, cfg["dark_status"], shots_dir, 610, 1254, meta[slug])

    # Pre-render masked headline lines for each beat
    b1_h = [render_serif_line_img(s, 72, accent_rgb, white_rgb) for s in cfg["b1_lines"]]
    b2_h = [render_serif_line_img(s, 70, accent_rgb, white_rgb) for s in cfg["b2_lines"]]
    b2_cards = [build_insight_card(n, ti, su, accent_rgb, card_fill) for n, ti, su in cfg["b2_cards"]]

    # Pre-render Beat 1 bespoke visual asset(s)
    b1_kind = cfg["b1_kind"]
    b1_assets: Dict[str, object] = {}
    if b1_kind == "pdf":
        b1_assets["card"] = build_beat1_visual_pdf_card(accent_rgb, card_fill)
    elif b1_kind == "dms":
        b1_assets["dms"] = [build_beat1_dm_bubble(txt, tm, accent_rgb, card_fill) for txt, tm in cfg["b1_dms"]]
    elif b1_kind == "maps":
        b1_assets["card"] = build_beat1_maps_card(accent_rgb, card_fill)
    elif b1_kind == "fragment":
        b1_assets["tiles"] = [build_beat1_fragment_tile(ti, su, accent_rgb, card_fill) for ti, su in cfg["b1_tiles"]]
    elif b1_kind == "reviews":
        b1_assets["card"] = build_beat1_reviews_card(accent_rgb, card_fill)

    # Pre-render Beat 3 floating callout pills
    b3_pills = [
        (t0, t1, build_floating_callout(lbl, accent_rgb, (card_fill[0], card_fill[1], card_fill[2], 236)))
        for t0, t1, lbl in cfg["b3_callouts"]
    ]

    # Pre-render End Card & Cover PNG (using crisp static hero phone preview inside 3:4 safe zone)
    hero_preview = phone.render(scroll_px=0.0, sheen_pos=0.42)
    cover_img = build_cover_endcard(
        backdrop=backdrop,
        kicker=cfg["b4_kicker"],
        title_lines=cfg["b4_lines"],
        price_line=cfg["b4_price"],
        cta_keyword=cfg["cta_keyword"],
        handle_line="@evacheecks  ·  evacheecks.github.io",
        accent_rgb=accent_rgb,
        card_fill=card_fill,
        preview_phone=hero_preview,
    )
    cover_path = out_dir / f"{fname}-cover.png"
    cover_img.convert("RGB").save(cover_path, "PNG", optimize=True)

    # Key scroll targets for Beat 3
    menu_sel = "#services" if slug == "linden-and-stone" else ("#prices" if slug == "northgate-barber-room" else "#menu")
    s_menu = phone.css_offset(menu_sel, 1100, top_margin_css=24)
    s_visit = phone.css_offset("#visit", 2200, top_margin_css=24)

    # Beat timestamps (continuous overlapping whip-pan transitions!)
    # Beat 1: 0.00 -> 2.85 (exits 2.62..2.92)
    # Beat 2: 2.66 -> 5.85 (enters 2.66..3.12, exits 5.58..5.90)
    # Beat 3: 5.64 -> 11.95 (enters 5.64..6.22, exits 11.68..12.02)
    # Beat 4: 11.74 -> 15.00 (enters 11.74..12.22, holds to 15.00)
    is_interactive = bool(cfg.get("interactive", False))
    tap_times_audio = [8.65, 10.10] if is_interactive else []
    whoosh_times = [2.76, 5.76, 11.84]

    def draw_beat1(canvas: Image.Image, t: float, exit_p: float) -> None:
        # Exit whips cleanly upward with directional vertical motion blur!
        ex_e = ease_in_cubic(exit_p)
        ex_dy = -ex_e * 1280.0
        ex_vel = -3.0 * (exit_p ** 2) * 1280.0 / (0.30 * FPS) if exit_p > 0.0 else 0.0
        a_out = clamp01(1.0 - exit_p * 1.15)
        if a_out <= 0.01:
            return

        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw_kicker_plain(layer, 360, cfg["b1_kicker"], accent_rgb, font_size=25, tracking=4.0, alpha=ease_out_cubic(t / 0.25))

        # Masked kinetic headline lines
        cy = 432
        for idx, limg in enumerate(b1_h):
            p = clamp01((t - (0.06 + idx * 0.11)) / 0.44)
            # Instantaneous vertical velocity blur during early rise
            vel_l = -42.0 * ((1.0 - p) ** 2.2) if 0.02 < p < 0.72 else 0.0
            composite_masked_line(layer, limg, cy, p, blur_dy=vel_l)
            cy += 84

        # Bespoke visual centerpiece
        if b1_kind == "pdf":
            cp = clamp01((t - 0.34) / 0.56)
            ce = ease_spring(cp, freq=1.5, decay=5.8)
            cdy = (1.0 - ce) * 260.0
            card = b1_assets["card"]
            if cp < 0.55:
                card = directional_blur_rgba(card, dy=(1.0 - cp) * 38.0)
            # Slight restless zoom wobble to sell "pinch-zoom frustration"
            wob = 1.0 + 0.018 * math.sin(max(0.0, t - 0.8) * 5.2)
            if abs(wob - 1.0) > 0.002 and cp > 0.5:
                nw, nh = int(card.width * wob), int(card.height * wob)
                card = card.resize((nw, nh), Image.Resampling.BILINEAR)
            paste_centered_xy(layer, apply_alpha(card, clamp01(cp * 2.6)), W / 2.0, 1080 + cdy)

        elif b1_kind == "dms":
            for idx, dm_card in enumerate(b1_assets["dms"]):
                st = 0.36 + idx * 0.36
                cp = clamp01((t - st) / 0.44)
                if cp <= 0.005:
                    continue
                ce = ease_out_back(cp, s=1.35)
                cdy = (1.0 - ce) * 140.0
                c_img = directional_blur_rgba(dm_card, dy=(1.0 - cp) * 32.0) if cp < 0.5 else dm_card
                paste_centered_xy(layer, apply_alpha(c_img, clamp01(cp * 3.0)), W / 2.0, 920 + idx * 168 + cdy)

        elif b1_kind == "maps":
            cp = clamp01((t - 0.34) / 0.52)
            ce = ease_spring(cp, freq=1.4, decay=6.0)
            cdy = (1.0 - ce) * 240.0
            card = directional_blur_rgba(b1_assets["card"], dy=(1.0 - cp) * 36.0) if cp < 0.52 else b1_assets["card"]
            paste_centered_xy(layer, apply_alpha(card, clamp01(cp * 2.8)), W / 2.0, 1040 + cdy)

        elif b1_kind == "fragment":
            for idx, tile in enumerate(b1_assets["tiles"]):
                st = 0.30 + idx * 0.24
                cp = clamp01((t - st) / 0.46)
                if cp <= 0.005:
                    continue
                ce = ease_out_expo(cp)
                dir_x = -1 if idx % 2 == 0 else 1
                dx_in = dir_x * (1.0 - ce) * 420.0
                drift_x = dir_x * math.sin(max(0.0, t - st) * 2.4 + idx) * 18.0
                t_img = directional_blur_rgba(tile, dx=(1.0 - cp) * 44.0) if cp < 0.48 else tile
                paste_centered_xy(layer, apply_alpha(t_img, clamp01(cp * 2.8)), W / 2.0 + dx_in + drift_x, 900 + idx * 172)

        elif b1_kind == "reviews":
            cp = clamp01((t - 0.32) / 0.54)
            ce = ease_spring(cp, freq=1.4, decay=5.8)
            cdy = (1.0 - ce) * 240.0
            card = directional_blur_rgba(b1_assets["card"], dy=(1.0 - cp) * 34.0) if cp < 0.50 else b1_assets["card"]
            paste_centered_xy(layer, apply_alpha(card, clamp01(cp * 2.8)), W / 2.0, 1020 + cdy)

        if abs(ex_vel) >= 4.0:
            layer = directional_blur_rgba(layer, dy=ex_vel)
        paste_alpha(canvas, apply_alpha(layer, a_out), 0, int(round(ex_dy)))

    def draw_beat2(canvas: Image.Image, lt: float, exit_p: float) -> None:
        # Enters via whip-up from below; exits via whip-up scatter
        en_p = clamp01(lt / 0.44)
        en_dy = (1.0 - ease_out_expo(en_p)) * 780.0
        en_vel = -46.0 * ((1.0 - en_p) ** 2.4) if en_p < 0.72 else 0.0

        ex_e = ease_in_cubic(exit_p)
        ex_dy = -ex_e * 1240.0
        ex_vel = -3.0 * (exit_p ** 2) * 1240.0 / (0.32 * FPS) if exit_p > 0.0 else 0.0

        a = clamp01(en_p * 3.0) * clamp01(1.0 - exit_p * 1.15)
        if a <= 0.01:
            return

        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw_kicker_plain(layer, 340, cfg["b2_kicker"], accent_rgb, font_size=25, tracking=4.0, alpha=clamp01(lt / 0.25))

        cy = 412
        for idx, limg in enumerate(b2_h):
            p = clamp01((lt - (0.04 + idx * 0.10)) / 0.44)
            composite_masked_line(layer, limg, cy, p)
            cy += 82

        # 3 Staggered spring-slammed insight cards with motion blur
        for idx, card in enumerate(b2_cards):
            st = 0.18 + idx * 0.22
            cp = clamp01((lt - st) / 0.46)
            if cp <= 0.005:
                continue
            ce = ease_out_back(cp, s=1.22)
            cdy = (1.0 - ce) * 220.0
            c_img = directional_blur_rgba(card, dy=(1.0 - cp) * 34.0) if cp < 0.48 else card
            paste_centered_xy(layer, apply_alpha(c_img, clamp01(cp * 3.0)), W / 2.0, 815 + idx * 212 + cdy)

        tot_vel = en_vel + ex_vel
        if abs(tot_vel) >= 4.0:
            layer = directional_blur_rgba(layer, dy=tot_vel)
        paste_alpha(canvas, apply_alpha(layer, a), 0, int(round(en_dy + ex_dy)))

    def draw_beat3(canvas: Image.Image, lt: float, exit_p: float) -> None:
        # Hero Android phone whips up with elastic overshoot + specular glass sweep!
        en_p = clamp01(lt / 0.56)
        en_e = ease_spring(en_p, freq=1.35, decay=5.8)
        en_dy = (1.0 - en_e) * 960.0
        en_vel = -58.0 * ((1.0 - en_p) ** 2.6) if en_p < 0.62 else 0.0

        ex_e = ease_in_cubic(exit_p)
        ex_dy = -ex_e * 1260.0
        ex_vel = -3.0 * (exit_p ** 2) * 1260.0 / (0.34 * FPS) if exit_p > 0.0 else 0.0

        a = clamp01(en_p * 3.2) * clamp01(1.0 - exit_p * 1.15)
        if a <= 0.01:
            return

        # Top editorial kicker (stays cleanly above phone)
        top_a = clamp01((lt - 0.12) / 0.30) * clamp01(1.0 - exit_p * 1.3)
        draw_kicker_plain(canvas, 178 + int(round(ex_dy * 0.5)), cfg["b3_kicker"], accent_rgb, font_size=23, tracking=3.8, alpha=top_a)

        # Diagonal specular glass light sweep runs right after entrance settles + subtle second glint
        sheen = None
        if 0.25 <= lt <= 1.65:
            sheen = (lt - 0.25) / 1.40
        elif 4.30 <= lt <= 5.60:
            sheen = (lt - 4.30) / 1.30

        touch_pt = None
        ripple = None
        state_img = None
        state_from = None
        state_blend = 1.0
        scroll_px = 0.0
        scroll_vel = 0.0

        if is_interactive and "book_sum_idle" in phone.states:
            # 0.0 -> 1.80: crisp hero + smooth flick down to menu
            # 1.80 -> 2.45: fast kinetic snap/scroll into live Booking Picker (book_sum_idle)
            # 2.45 -> 3.05: touch cursor glides to time slot, taps at lt=3.00 (t=8.64s) -> live selected state!
            # 3.05 -> 4.50: touch cursor glides down to Confirm button, taps at lt=4.45 (t=10.09s) -> live confirmed!
            tx_t, ty_t = cfg["tap_time_xy"]
            tx_c, ty_c = cfg["tap_confirm_xy"]

            if lt < 2.25:
                if lt < 0.75:
                    scroll_px = 0.0
                else:
                    sp = clamp01((lt - 0.75) / 1.45)
                    scroll_px = lerp(0.0, float(s_menu), ease_in_out_cubic(sp))
                    # Derivative approx for scroll motion blur
                    sp2 = clamp01((lt + 1.0 / FPS - 0.75) / 1.45)
                    scroll_vel = lerp(0.0, float(s_menu), ease_in_out_cubic(sp2)) - scroll_px
                    # Subtle flick cursor
                    if 0.78 <= lt <= 1.65:
                        fp = (lt - 0.78) / 0.87
                        touch_pt = (0.72, lerp(0.74, 0.36, ease_out_cubic(fp)), 0.65 * math.sin(math.pi * fp))
            elif lt < 2.55:
                # Smooth cross-whip into interactive booking picker viewport
                bp = clamp01((lt - 2.25) / 0.30)
                state_img = phone.states["book_sum_idle"]
                scroll_vel = 36.0 * math.sin(math.pi * bp)
            elif lt < 3.02:
                # Cursor glides smoothly onto open time slot chip
                state_img = phone.states["book_sum_idle"]
                gp = clamp01((lt - 2.55) / 0.42)
                e = ease_in_out_cubic(gp)
                cx = lerp(0.80, tx_t, e)
                cy = lerp(0.68, ty_t, e) - 0.04 * math.sin(math.pi * e)
                press = clamp01((lt - 2.94) / 0.08)
                touch_pt = (cx, cy, press)
            elif lt < 4.46:
                # Time slot tapped! Ripple expands + screen pops cleanly to selected state!
                age = clamp01((lt - 3.02) / 0.55)
                ripple = (tx_t, ty_t, age)
                state_from = phone.states["book_sum_idle"]
                state_img = phone.states["book_sum_selected"]
                state_blend = clamp01((lt - 3.02) / 0.14)
                # Cursor releases, pauses briefly, then glides smoothly down to Confirm button
                if lt < 3.55:
                    press = clamp01(1.0 - (lt - 3.02) / 0.14)
                    touch_pt = (tx_t, ty_t, press)
                else:
                    gp = clamp01((lt - 3.55) / 0.78)
                    e = ease_in_out_cubic(gp)
                    cx = lerp(tx_t, tx_c, e) + 0.05 * math.sin(math.pi * e)
                    cy = lerp(ty_t, ty_c, e)
                    press = clamp01((lt - 4.38) / 0.08)
                    touch_pt = (cx, cy, press)
            else:
                # Confirm button tapped! Ripple expands + live confirmation banner appears!
                age = clamp01((lt - 4.46) / 0.58)
                ripple = (tx_c, ty_c, age)
                state_from = phone.states["book_sum_selected"]
                state_img = phone.states["book_sum_confirmed"]
                state_blend = clamp01((lt - 4.46) / 0.18)
                if lt < 5.05:
                    press = clamp01(1.0 - (lt - 4.46) / 0.14)
                    touch_pt = (tx_c, ty_c, press)
        else:
            # Smooth physics-driven 2-stage flick-scroll through Hero -> Menu -> Visit/Hours
            if lt < 0.85:
                scroll_px = 0.0
            elif lt < 3.45:
                sp = clamp01((lt - 0.85) / 2.45)
                scroll_px = lerp(0.0, float(s_menu), ease_in_out_cubic(sp))
                sp2 = clamp01((lt + 1.0 / FPS - 0.85) / 2.45)
                scroll_vel = lerp(0.0, float(s_menu), ease_in_out_cubic(sp2)) - scroll_px
                if 0.90 <= lt <= 1.85:
                    fp = (lt - 0.90) / 0.95
                    touch_pt = (0.74, lerp(0.75, 0.34, ease_out_cubic(fp)), 0.7 * math.sin(math.pi * fp))
            else:
                sp = clamp01((lt - 3.45) / 2.25)
                scroll_px = lerp(float(s_menu), float(s_visit), ease_in_out_cubic(sp))
                sp2 = clamp01((lt + 1.0 / FPS - 3.45) / 2.25)
                scroll_vel = lerp(float(s_menu), float(s_visit), ease_in_out_cubic(sp2)) - scroll_px
                if 3.50 <= lt <= 4.35:
                    fp = (lt - 3.50) / 0.85
                    touch_pt = (0.74, lerp(0.72, 0.36, ease_out_cubic(fp)), 0.7 * math.sin(math.pi * fp))

        phone_img = phone.render(
            scroll_px=scroll_px,
            scroll_vel_px=scroll_vel,
            state_img=state_img,
            state_blend_from=state_from,
            state_blend_t=state_blend,
            sheen_pos=sheen,
            touch_pt=touch_pt,
            ripple=ripple,
            accent_rgb=accent_rgb,
        )

        # Gentle 3D-feel subtle floating motion during hold
        float_y = math.sin(lt * 1.7) * 5.0
        tot_vel = en_vel + ex_vel
        if abs(tot_vel) >= 4.0:
            phone_img = directional_blur_rgba(phone_img, dy=tot_vel)

        paste_centered_xy(canvas, apply_alpha(phone_img, a), W / 2.0, 912 + en_dy + ex_dy + float_y)

        # Animated floating section callout pill below phone
        for pt0, pt1, pill_img in b3_pills:
            if pt0 <= lt <= pt1 + 0.25:
                pin = clamp01((lt - pt0) / 0.30)
                pout = clamp01((pt1 - lt) / 0.22) if lt > pt1 - 0.22 else 1.0
                pa = pin * pout * clamp01(1.0 - exit_p * 1.4)
                if pa > 0.01:
                    pdy = (1.0 - ease_out_back(pin, s=1.2)) * 42.0
                    paste_centered_xy(canvas, apply_alpha(pill_img, pa), W / 2.0, 1690 + pdy + ex_dy * 0.65)

    def draw_beat4(canvas: Image.Image, lt: float) -> None:
        en_p = clamp01(lt / 0.48)
        if en_p >= 0.999:
            canvas.alpha_composite(cover_img)
            return
        en_dy = (1.0 - ease_out_expo(en_p)) * 840.0
        en_vel = -50.0 * ((1.0 - en_p) ** 2.4) if en_p < 0.70 else 0.0
        src = directional_blur_rgba(cover_img, dy=en_vel) if abs(en_vel) >= 4.0 else cover_img
        paste_alpha(canvas, apply_alpha(src, clamp01(en_p * 2.8)), 0, int(round(en_dy)))

    def render_bg(t: float) -> Image.Image:
        cam_shift = 0.0
        if 2.62 <= t <= 3.12:
            cam_shift = math.sin(math.pi * clamp01((t - 2.62) / 0.50)) * 340.0
        elif 5.58 <= t <= 6.18:
            cam_shift = math.sin(math.pi * clamp01((t - 5.58) / 0.60)) * 420.0
        elif 11.68 <= t <= 12.22:
            cam_shift = math.sin(math.pi * clamp01((t - 11.68) / 0.54)) * 360.0
        return backdrop.render(t, cam_shift_y=cam_shift)

    def render_at_time(t: float, bg_img: Optional[Image.Image] = None) -> Image.Image:
        canvas = bg_img if bg_img is not None else render_bg(t)

        if t < 2.94:
            ex = clamp01((t - 2.62) / 0.30)
            draw_beat1(canvas, t, ex)
        if 2.66 <= t < 5.92:
            ex = clamp01((t - 5.58) / 0.32)
            draw_beat2(canvas, t - 2.66, ex)
        if 5.64 <= t < 12.04:
            ex = clamp01((t - 11.68) / 0.34)
            draw_beat3(canvas, t - 5.64, ex)
        if t >= 11.74:
            draw_beat4(canvas, t - 11.74)

        draw_progress_hairline(canvas, t / DURATION_SEC, accent_rgb)
        return canvas

    def sample_count(t: float) -> int:
        # 5-sample 200-deg linear-light shutter on whip-pan cuts & slams;
        # 3-sample on staggered card pop-ins & interactive touch-cursor arcs;
        # 1-sample elsewhere (linear phone scrolls use continuous 2-pass premultiplied directional blur!)
        if (
            (0.04 <= t <= 0.58)
            or (2.62 <= t <= 3.10)
            or (5.58 <= t <= 6.20)
            or (11.68 <= t <= 12.22)
        ):
            return 5
        if (3.10 < t <= 3.74) or (is_interactive and ((8.16 <= t <= 8.84) or (9.22 <= t <= 10.30))):
            return 3
        return 1

    return _encode_reel_mp4(
        fname=fname,
        out_dir=out_dir,
        render_at_time=render_at_time,
        render_bg=render_bg,
        sample_count=sample_count,
        chords=cfg["chords"],
        whoosh_times=whoosh_times,
        tap_times=tap_times_audio,
        seed=cfg["seed"],
        cover_path=cover_path,
        t_start=t_start,
        label=f"Reel {rid}",
    )


# ---------------------------------------------------------------------------
# Reel 13: Multi-Style 5-Demo Motion-Blurred Whip Carousel + 3-Phone Studio Showcase
# ---------------------------------------------------------------------------
def render_reel13_showcase(shots_dir: Path, meta: dict, out_dir: Path) -> Tuple[Path, Path]:
    t_start = time.time()
    fname = "eva-reel-13-studio-showcase-free-mockup"
    accent_rgb = hex_rgb("#3cd9a8")
    white_rgb = (246, 249, 248)
    card_fill = (24, 34, 39, 236)

    backdrop = StudioBackdrop("#101a20", "#070b0e", "#3cd9a8", seed=13)

    # Load all 5 upgraded demos for the rapid horizontal motion-blurred whip carousel!
    carousel_specs = [
        ("harbor-street-coffee", False, "CAFES & BAKERIES  ·  HARBOR STREET"),
        ("linden-and-stone", False, "SALONS & NAILS  ·  LINDEN & STONE"),
        ("northgate-barber-room", True, "BARBERSHOPS  ·  NORTHGATE BARBER"),
        ("saffron-and-salt", True, "GRILLS & TAKEAWAYS  ·  SAFFRON & SALT"),
        ("the-copper-kettle", False, "LOCAL SHOPS  ·  THE COPPER KETTLE"),
    ]
    carousel_phones = [
        (StudioPhoneAsset(sl, dk, shots_dir, 580, 1192, meta[sl]), lbl)
        for sl, dk, lbl in carousel_specs
    ]
    # Pre-render static crisp hero phone frames for lightning-fast horizontal whip carousel
    carousel_rendered = [
        (p.render(scroll_px=0.0, sheen_pos=0.45), build_floating_callout(lbl, accent_rgb, (22, 32, 37, 238)))
        for p, lbl in carousel_phones
    ]

    # Trio of scrolling phones for Beat 3 Studio Fan Showcase
    fan_left = StudioPhoneAsset("linden-and-stone", False, shots_dir, 390, 800, meta["linden-and-stone"])
    fan_mid = StudioPhoneAsset("northgate-barber-room", True, shots_dir, 430, 884, meta["northgate-barber-room"])
    fan_right = StudioPhoneAsset("harbor-street-coffee", False, shots_dir, 390, 800, meta["harbor-street-coffee"])

    b1_h = [
        render_serif_line_img([("Zero ", False), ("generic", True)], 82, accent_rgb, white_rgb),
        render_serif_line_img([("templates.", False)], 82, accent_rgb, white_rgb),
    ]
    b1_sub = build_floating_callout("5 LOCAL NICHES  ·  5 DISTINCT BRANDS", accent_rgb, (24, 34, 39, 238))

    b3_h = [
        render_serif_line_img([("See your shop ", False), ("live", True)], 68, accent_rgb, white_rgb),
        render_serif_line_img([("before you pay.", False)], 68, accent_rgb, white_rgb),
    ]
    b3_steps = [
        build_insight_card("01", "Free preview first", "We design a working mockup of your shop", accent_rgb, card_fill),
        build_insight_card("02", "Fixed from $50", "Agreed up front — zero monthly retainers", accent_rgb, card_fill),
    ]

    # End Card & Cover PNG (3:4 safe zone with crisp mini 3-phone fanned preview!)
    cover_fan = Image.new("RGBA", (900, 610), (0, 0, 0, 0))
    cf_l = fan_left.render(scroll_px=0.0, sheen_pos=0.45)
    cf_l = cf_l.resize((int(cf_l.width * 0.54), int(cf_l.height * 0.54)), Image.Resampling.LANCZOS).rotate(8.5, resample=Image.Resampling.BICUBIC, expand=True)
    cf_r = fan_right.render(scroll_px=0.0, sheen_pos=0.45)
    cf_r = cf_r.resize((int(cf_r.width * 0.54), int(cf_r.height * 0.54)), Image.Resampling.LANCZOS).rotate(-8.5, resample=Image.Resampling.BICUBIC, expand=True)
    cf_m = fan_mid.render(scroll_px=0.0, sheen_pos=0.45)
    cf_m = cf_m.resize((int(cf_m.width * 0.56), int(cf_m.height * 0.56)), Image.Resampling.LANCZOS)
    paste_centered_xy(cover_fan, cf_l, 232.0, 326.0)
    paste_centered_xy(cover_fan, cf_r, 668.0, 326.0)
    paste_centered_xy(cover_fan, cf_m, 450.0, 304.0)

    cover_img = build_cover_endcard(
        backdrop=backdrop,
        kicker="CUSTOM ONE-PAGE WEBSITES",
        title_lines=[
            [("See your shop ", False), ("live", True)],
            [("before you pay.", False)],
        ],
        price_line="Fixed from $50  ·  Live in 2-3 days",
        cta_keyword="DEMO",
        handle_line="@evacheecks  ·  evacheecks.github.io",
        accent_rgb=accent_rgb,
        card_fill=card_fill,
        preview_phone=cover_fan,
        preview_prebuilt=True,
    )
    cover_path = out_dir / f"{fname}-cover.png"
    cover_img.convert("RGB").save(cover_path, "PNG", optimize=True)

    # Audio cues synced to whip-up + rapid horizontal carousel swipes + end card whip
    whoosh_times = [2.25, 3.12, 3.88, 4.64, 5.40, 6.26, 11.78]
    chords = [
        [164.81, 246.94, 329.63, 392.00],  # Em7
        [196.00, 246.94, 293.66, 369.99],  # G maj7
        [130.81, 196.00, 246.94, 329.63],  # C maj7
        [146.83, 220.00, 293.66, 369.99],  # D maj
    ]

    # Scroll distances for Beat 3 studio fan
    l_end = fan_left.css_offset("#services", 1400)
    m_end = fan_mid.css_offset("#prices", 1040)
    r_end = fan_right.css_offset("#menu", 1290)

    def render_bg(t: float) -> Image.Image:
        cam_shift = 0.0
        if 2.12 <= t <= 2.58:
            cam_shift = math.sin(math.pi * clamp01((t - 2.12) / 0.46)) * 340.0
        elif 6.14 <= t <= 6.72:
            cam_shift = math.sin(math.pi * clamp01((t - 6.14) / 0.58)) * 400.0
        elif 11.66 <= t <= 12.20:
            cam_shift = math.sin(math.pi * clamp01((t - 11.66) / 0.54)) * 360.0
        return backdrop.render(t, cam_shift_y=cam_shift)

    def render_at_time(t: float, bg_img: Optional[Image.Image] = None) -> Image.Image:
        canvas = bg_img if bg_img is not None else render_bg(t)

        # Beat 1: 0.00 -> 2.40 (High-impact kinetic title slam)
        if t < 2.42:
            ex = clamp01((t - 2.12) / 0.28)
            ex_dy = -ease_in_cubic(ex) * 1240.0
            ex_vel = -3.0 * (ex ** 2) * 1240.0 / (0.28 * FPS) if ex > 0.0 else 0.0
            a = clamp01(1.0 - ex * 1.15)
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            draw_kicker_plain(layer, 640, "BUILT FOR LOCAL BUSINESSES", accent_rgb, font_size=26, tracking=4.2, alpha=ease_out_cubic(t / 0.24))
            for idx, limg in enumerate(b1_h):
                p = clamp01((t - (0.08 + idx * 0.12)) / 0.44)
                composite_masked_line(layer, limg, 718 + idx * 96, p, blur_dy=-40.0 * ((1.0 - p) ** 2) if p < 0.6 else 0.0)
            sp = clamp01((t - 0.42) / 0.46)
            if sp > 0.01:
                pdy = (1.0 - ease_out_back(sp, s=1.3)) * 80.0
                paste_centered_xy(layer, apply_alpha(b1_sub, clamp01(sp * 2.5)), W / 2.0, 995 + pdy)
            if abs(ex_vel) >= 4.0:
                layer = directional_blur_rgba(layer, dy=ex_vel)
            paste_alpha(canvas, apply_alpha(layer, a), 0, int(round(ex_dy)))

        # Beat 2: 2.16 -> 6.40 (RAPID 5-STYLE HORIZONTAL MOTION-BLURRED WHIP CAROUSEL!)
        if 2.16 <= t < 6.45:
            lt = t - 2.16
            en_p = clamp01(lt / 0.40)
            en_dy = (1.0 - ease_out_expo(en_p)) * 900.0
            ex_p = clamp01((t - 6.14) / 0.30)
            ex_dy = -ease_in_cubic(ex_p) * 1220.0
            a = clamp01(en_p * 3.0) * clamp01(1.0 - ex_p * 1.15)

            draw_kicker_plain(canvas, 180 + int(round(ex_dy * 0.5)), "5 CUSTOM DESIGNS  ·  ZERO TEMPLATES", accent_rgb, font_size=24, tracking=3.8, alpha=a)

            # 5 slides across 4.0s -> 0.76s per slide, with 0.26s ultra-fast horizontal whip-swipe!
            slot_dur = 0.76
            pos = lt / slot_dur
            idx = min(4, int(pos))
            frac = pos - idx

            # Horizontal whip transition between idx and idx+1 in the last 0.26s of each slot
            swipe_start = 0.66
            if idx < 4 and frac > swipe_start:
                sw = clamp01((frac - swipe_start) / (1.0 - swipe_start))
                sw_e = ease_in_out_quint(sw)
                # Peak horizontal velocity for genuine cinema lateral motion blur!
                vel_x = -math.sin(math.pi * sw) * 86.0
                x_cur = W / 2.0 - sw_e * 1080.0
                x_nxt = W / 2.0 + (1.0 - sw_e) * 1080.0

                p_cur, lbl_cur = carousel_rendered[idx]
                p_nxt, lbl_nxt = carousel_rendered[idx + 1]
                if abs(vel_x) >= 4.0:
                    p_cur = directional_blur_rgba(p_cur, dx=vel_x)
                    p_nxt = directional_blur_rgba(p_nxt, dx=vel_x)
                paste_centered_xy(canvas, apply_alpha(p_cur, a), x_cur, 892 + en_dy + ex_dy)
                paste_centered_xy(canvas, apply_alpha(p_nxt, a), x_nxt, 892 + en_dy + ex_dy)
                # Label cross-slide
                paste_centered_xy(canvas, apply_alpha(lbl_cur, a * (1.0 - sw_e)), W / 2.0 - sw_e * 160.0, 1656 + ex_dy * 0.6)
                paste_centered_xy(canvas, apply_alpha(lbl_nxt, a * sw_e), W / 2.0 + (1.0 - sw_e) * 160.0, 1656 + ex_dy * 0.6)
            else:
                p_cur, lbl_cur = carousel_rendered[idx]
                if en_p < 0.68:
                    p_cur = directional_blur_rgba(p_cur, dy=-48.0 * ((1.0 - en_p) ** 2.2))
                elif ex_p > 0.02:
                    p_cur = directional_blur_rgba(p_cur, dy=-64.0 * (ex_p ** 2))
                paste_centered_xy(canvas, apply_alpha(p_cur, a), W / 2.0, 892 + en_dy + ex_dy)
                paste_centered_xy(canvas, apply_alpha(lbl_cur, a), W / 2.0, 1656 + en_dy * 0.4 + ex_dy * 0.6)

        # Beat 3: 6.20 -> 11.98 (3-Phone Fanned Studio Showcase + Free Preview Offer)
        if 6.20 <= t < 12.00:
            lt = t - 6.20
            en_p = clamp01(lt / 0.56)
            en_e = ease_spring(en_p, freq=1.35, decay=5.8)
            en_dy = (1.0 - en_e) * 780.0
            ex_p = clamp01((t - 11.66) / 0.32)
            ex_dy = -ease_in_cubic(ex_p) * 1240.0
            a = clamp01(en_p * 3.0) * clamp01(1.0 - ex_p * 1.15)

            draw_kicker_plain(canvas, 178 + int(round(ex_dy * 0.5)), "BUILT TO ORDER  ·  FREE PREVIEW", accent_rgb, font_size=23, tracking=3.8, alpha=a)
            for idx, limg in enumerate(b3_h):
                p = clamp01((lt - (0.06 + idx * 0.10)) / 0.44)
                composite_masked_line(canvas, limg, 232 + idx * 76 + int(round(ex_dy * 0.5)), p)

            # Synchronized smooth scrolling across 3 fanned phones with continuous scroll blur
            prog = ease_in_out_cubic(clamp01((lt - 0.60) / 4.80))
            prog2 = ease_in_out_cubic(clamp01((lt + 1.0 / FPS - 0.60) / 4.80))
            dprog = prog2 - prog
            sheen = (lt - 0.40) / 1.40 if 0.40 <= lt <= 1.80 else None
            pl = fan_left.render(scroll_px=lerp(0.0, float(l_end), prog), scroll_vel_px=float(l_end) * dprog, sheen_pos=sheen).rotate(6.5, resample=Image.Resampling.BICUBIC, expand=True)
            pr = fan_right.render(scroll_px=lerp(0.0, float(r_end), prog), scroll_vel_px=float(r_end) * dprog, sheen_pos=sheen).rotate(-6.5, resample=Image.Resampling.BICUBIC, expand=True)
            pm = fan_mid.render(scroll_px=lerp(0.0, float(m_end), prog), scroll_vel_px=float(m_end) * dprog, sheen_pos=sheen)

            fan_spread = ease_out_expo(clamp01((lt - 0.08) / 0.52))
            lx = lerp(W / 2.0, 214.0, fan_spread)
            rx = lerp(W / 2.0, 866.0, fan_spread)
            if en_p < 0.52 or ex_p > 0.05:
                v_blur = -42.0 * ((1.0 - en_p) ** 2) if en_p < 0.52 else -62.0 * (ex_p ** 2)
                pm = directional_blur_rgba(pm, dy=v_blur)

            paste_centered_xy(canvas, apply_alpha(pl, a), lx, 916 + en_dy + ex_dy + math.sin(lt * 1.6) * 5.0)
            paste_centered_xy(canvas, apply_alpha(pr, a), rx, 916 + en_dy + ex_dy - math.sin(lt * 1.6) * 5.0)
            paste_centered_xy(canvas, apply_alpha(pm, a), W / 2.0, 880 + en_dy * 0.85 + ex_dy)

            # Two sleek offer step cards smoothly rising below the 3-phone fan
            for idx, st_card in enumerate(b3_steps):
                sp = clamp01((lt - (0.38 + idx * 0.24)) / 0.44)
                if sp > 0.01:
                    sdy = (1.0 - ease_out_back(sp, s=1.18)) * 90.0
                    paste_centered_xy(canvas, apply_alpha(st_card, a * clamp01(sp * 2.8)), W / 2.0, 1468 + idx * 196 + sdy + ex_dy * 0.7)

        # Beat 4: 11.72 -> 15.00 (Clean 3:4 Safe End Card / Cover)
        if t >= 11.72:
            lt = t - 11.72
            en_p = clamp01(lt / 0.48)
            if en_p >= 0.999:
                canvas.alpha_composite(cover_img)
            else:
                en_dy = (1.0 - ease_out_expo(en_p)) * 840.0
                en_vel = -50.0 * ((1.0 - en_p) ** 2.4) if en_p < 0.70 else 0.0
                src = directional_blur_rgba(cover_img, dy=en_vel) if abs(en_vel) >= 4.0 else cover_img
                paste_alpha(canvas, apply_alpha(src, clamp01(en_p * 2.8)), 0, int(round(en_dy)))

        draw_progress_hairline(canvas, t / DURATION_SEC, accent_rgb)
        return canvas

    def sample_count(t: float) -> int:
        # 5-sample 200-deg linear-light shutter on kinetic slams, whip-cuts, and EVERY active horizontal whip-swipe!
        if (
            (0.04 <= t <= 0.58)
            or (2.12 <= t <= 2.58)
            or (6.12 <= t <= 6.84)
            or (11.66 <= t <= 12.22)
        ):
            return 5
        if 2.16 <= t < 6.14:
            pos = (t - 2.16) / 0.76
            idx = min(4, int(pos))
            frac = pos - idx
            if idx < 4 and frac >= 0.62:
                return 5
        return 1

    return _encode_reel_mp4(
        fname=fname,
        out_dir=out_dir,
        render_at_time=render_at_time,
        render_bg=render_bg,
        sample_count=sample_count,
        chords=chords,
        whoosh_times=whoosh_times,
        tap_times=[],
        seed=13,
        cover_path=cover_path,
        t_start=t_start,
        label="Reel 13",
    )


def _encode_reel_mp4(
    fname: str,
    out_dir: Path,
    render_at_time: Callable[[float, Optional[Image.Image]], Image.Image],
    render_bg: Callable[[float], Image.Image],
    sample_count: Callable[[float], int],
    chords: List[List[float]],
    whoosh_times: List[float],
    tap_times: List[float],
    seed: int,
    cover_path: Path,
    t_start: float,
    label: str,
) -> Tuple[Path, Path]:
    wav_path = out_dir / f"{fname}.wav"
    mp4_path = out_dir / f"{fname}.mp4"
    synthesize_studio_audio(wav_path, chords, whoosh_times, tap_times, seed=seed)

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", str(wav_path),
        "-c:v", "libx264", "-profile:v", "high", "-level:v", "4.1",
        "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart", "-shortest",
        str(mp4_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None

    for fidx in range(TOTAL_FRAMES):
        t = fidx / float(FPS)
        sc = sample_count(t)
        rgb = render_shutter_frame(render_at_time, t, samples=sc, shutter_angle=200.0, bg_fn=render_bg)
        proc.stdin.write(rgb.tobytes())
        if (fidx + 1) % 150 == 0:
            print(f"[{label}] {fidx + 1}/{TOTAL_FRAMES} frames ({time.time() - t_start:.1f}s)", flush=True)

    proc.stdin.close()
    ret = proc.wait()
    wav_path.unlink(missing_ok=True)
    if ret != 0:
        raise RuntimeError(f"ffmpeg failed for {label} with code {ret}")
    elapsed = time.time() - t_start
    print(f"[{label}] Saved {mp4_path.name} ({mp4_path.stat().st_size // 1024} KB) + {cover_path.name} in {elapsed:.1f}s", flush=True)
    return mp4_path, cover_path


def run_preflight_glyph_check() -> None:
    """Verify zero missing/tofu glyphs across every rendered string in Reels 08–13."""
    texts: List[str] = [
        "@evacheecks · evacheecks.github.io",
        "Fictional demo design · No obligation preview",
        "BUILT FOR LOCAL BUSINESSES",
        "5 LOCAL NICHES · 5 DISTINCT BRANDS",
        "5 CUSTOM DESIGNS · ZERO TEMPLATES",
        "BUILT TO ORDER · FREE PREVIEW",
        "CUSTOM ONE-PAGE WEBSITES",
        'COMMENT "DEMO" FOR A FREE MOCKUP',
        "Fixed from $50 · Live in 2-3 days",
        "menu_final_v3_scan.pdf (6.8 MB)",
        "PINCH. ZOOM. LEAVE.",
        "4.8 · 400+ LOCAL REVIEWS",
        "Still sending customers to Facebook?",
    ]
    for cfg in REEL_SPECS:
        texts.extend([
            cfg["b1_kicker"], cfg["b2_kicker"], cfg["b3_kicker"], cfg["b4_kicker"],
            cfg["b4_price"], f'COMMENT "{cfg["cta_keyword"]}" FOR A FREE MOCKUP',
        ])
        for grp in (cfg["b1_lines"], cfg["b2_lines"], cfg["b4_lines"]):
            for segs in grp:
                for txt, _ in segs:
                    texts.append(txt)
        for _, ti, su in cfg["b2_cards"]:
            texts.extend([ti, su])
        for _, _, lbl in cfg["b3_callouts"]:
            texts.append(lbl)
        for txt, tm in cfg.get("b1_dms", []):
            texts.extend([txt, tm])
        for ti, su in cfg.get("b1_tiles", []):
            texts.extend([ti, su])

    f_serif = font(FONT_SERIF_BOLD, 42)
    f_sans = font(FONT_SANS_MED, 28)
    for txt in texts:
        for ch in txt:
            if ch in (" ", "\n", "\t"):
                continue
            if not f_sans.getmask(ch).getbbox() and not f_serif.getmask(ch).getbbox():
                raise RuntimeError(f"Missing glyph {ch!r} in text: {txt!r}")
    print("Preflight glyph check PASSED (0 missing glyphs).", flush=True)


def _worker_render(task_id: str, shots_dir_str: str, meta: dict, out_dir_str: str) -> Tuple[str, str]:
    shots_dir = Path(shots_dir_str)
    out_dir = Path(out_dir_str)
    if task_id == "13":
        mp4, cov = render_reel13_showcase(shots_dir, meta, out_dir)
        return str(mp4), str(cov)
    for cfg in REEL_SPECS:
        if cfg["id"] == task_id:
            mp4, cov = render_vertical_reel(cfg, shots_dir, meta, out_dir)
            return str(mp4), str(cov)
    raise ValueError(f"Unknown reel id {task_id}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate studio-quality motion-blurred Reels 08–13 & Cover PNGs")
    ap.add_argument("--shots-dir", type=Path, default=DEFAULT_SHOTS_DIR)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--only", nargs="*", help="Subset of reel IDs (08 09 10 11 12 13)")
    ap.add_argument("--workers", type=int, default=2, help="Parallel worker processes")
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    run_preflight_glyph_check()

    meta_path = args.shots_dir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"Missing {meta_path}. Capture updated demo screenshots first.")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    target_ids = args.only if args.only else ["08", "09", "10", "11", "12", "13"]
    t0 = time.time()
    if args.workers > 1 and len(target_ids) > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(_worker_render, rid, str(args.shots_dir), meta, str(args.out_dir)) for rid in target_ids]
            for fut in as_completed(futs):
                fut.result()
    else:
        for rid in target_ids:
            _worker_render(rid, str(args.shots_dir), meta, str(args.out_dir))

    print(f"\nAll {len(target_ids)} studio Reels finished in {time.time() - t0:.1f}s -> {args.out_dir}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
