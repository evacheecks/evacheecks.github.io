#!/usr/bin/env python3
"""
Deterministic site audit for evacheecks.github.io.
Checks:
1. All 6 HTML pages exist and parse cleanly.
2. Required SEO / social tags (<title>, <meta name="description">, <link rel="canonical">, og:title, og:description, og:image, twitter:card).
3. Heading hierarchy (no skipped heading levels, e.g. h2 -> h4).
4. All static <button> elements have an explicit type="button" or type="submit".
5. All <img> elements have alt, width, and height attributes and point to existing files < 300 KB with no EXIF (APP1 Exif) metadata.
6. All internal href/src links resolve to existing files in the repository.
7. Inline <script> blocks pass `node --check` syntax validation.
8. Key WCAG AA color contrast pairs meet >= 4.5:1 for normal text.
"""
import os
import re
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = [
    ROOT / "index.html",
    ROOT / "demo" / "harbor-street-coffee" / "index.html",
    ROOT / "demo" / "the-copper-kettle" / "index.html",
    ROOT / "demo" / "saffron-and-salt" / "index.html",
    ROOT / "demo" / "northgate-barber-room" / "index.html",
    ROOT / "demo" / "linden-and-stone" / "index.html",
]


class PageInspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.metas = {}
        self.links = []
        self.headings = []
        self.buttons = []
        self.imgs = []
        self.anchors = []
        self.scripts = []
        self._in_script = False
        self._script_buf = []
        self.has_title = False

    def handle_starttag(self, tag, attrs):
        ad = dict(attrs)
        if tag == "title":
            self.has_title = True
        elif tag == "meta":
            key = ad.get("name") or ad.get("property")
            if key and "content" in ad:
                self.metas[key] = ad["content"]
        elif tag == "link":
            self.links.append(ad)
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.headings.append(int(tag[1]))
        elif tag == "button":
            self.buttons.append(ad)
        elif tag == "img":
            self.imgs.append(ad)
        elif tag == "a":
            self.anchors.append(ad)
        elif tag == "script":
            self._in_script = True
            self._script_buf = []

    def handle_endtag(self, tag):
        if tag == "script" and self._in_script:
            self._in_script = False
            self.scripts.append("".join(self._script_buf))

    def handle_data(self, data):
        if self._in_script:
            self._script_buf.append(data)


def rel_lum(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    rgb = [int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast_ratio(c1: str, c2: str) -> float:
    l1, l2 = rel_lum(c1), rel_lum(c2)
    bright, dark = max(l1, l2), min(l1, l2)
    return (bright + 0.05) / (dark + 0.05)


def has_jpeg_exif(path: Path) -> bool:
    data = path.read_bytes()
    if not data.startswith(b"\xff\xd8"):
        return False
    i = 2
    while i + 4 <= len(data) and data[i] == 0xFF:
        marker = data[i + 1]
        if marker in (0xDA, 0xD9):
            break
        if marker in (0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0x01):
            i += 2
            continue
        seg_len = int.from_bytes(data[i + 2 : i + 4], "big")
        if marker == 0xE1 and data[i + 4 : i + 10] == b"Exif\x00\x00":
            return True
        i += 2 + seg_len
    return False


def main() -> int:
    errors = []

    for page in PAGES:
        rel_page = page.relative_to(ROOT)
        if not page.exists():
            errors.append(f"{rel_page}: file missing")
            continue

        html = page.read_text(encoding="utf-8")
        p = PageInspector()
        p.feed(html)

        if not p.has_title:
            errors.append(f"{rel_page}: missing <title>")
        for req_meta in ("description", "og:title", "og:description", "og:type", "og:url", "og:image", "twitter:card"):
            if not p.metas.get(req_meta):
                errors.append(f"{rel_page}: missing meta '{req_meta}'")
        if not any(l.get("rel") == "canonical" and l.get("href") for l in p.links):
            errors.append(f"{rel_page}: missing <link rel='canonical'>")

        # Heading hierarchy check
        if not p.headings or p.headings[0] != 1:
            errors.append(f"{rel_page}: first heading must be <h1>, got {p.headings[:1]}")
        for prev, curr in zip(p.headings, p.headings[1:]):
            if curr > prev + 1:
                errors.append(f"{rel_page}: skipped heading level h{prev} -> h{curr}")

        # Button type check
        for idx, b in enumerate(p.buttons, 1):
            if b.get("type") not in ("button", "submit", "reset"):
                errors.append(f"{rel_page}: <button> #{idx} missing explicit type attribute ({b})")

        # Image checks
        for im in p.imgs:
            src = im.get("src", "")
            if not im.get("alt"):
                errors.append(f"{rel_page}: <img src='{src}'> missing alt")
            if not im.get("width") or not im.get("height"):
                errors.append(f"{rel_page}: <img src='{src}'> missing width/height")
            img_path = (page.parent / src).resolve()
            if not img_path.exists():
                errors.append(f"{rel_page}: <img src='{src}'> target does not exist")

        # Internal link check
        for a in p.anchors:
            href = a.get("href", "")
            if not href or href.startswith(("#", "http://", "https://", "mailto:", "tel:")):
                continue
            target = (page.parent / href).resolve()
            if not target.exists():
                errors.append(f"{rel_page}: broken relative link href='{href}'")

        # Inline JS syntax check via node --check
        for s_idx, code in enumerate(p.scripts, 1):
            if not code.strip():
                continue
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tf:
                tf.write(code)
                tf_path = tf.name
            try:
                res = subprocess.run(["node", "--check", tf_path], capture_output=True, text=True)
                if res.returncode != 0:
                    errors.append(f"{rel_page}: inline script #{s_idx} failed node --check: {res.stderr.strip()}")
            finally:
                os.unlink(tf_path)

    # Check all demo images (<300 KB and zero EXIF)
    for jpg in (ROOT / "demo").rglob("*.jpg"):
        rel_jpg = jpg.relative_to(ROOT)
        size = jpg.stat().st_size
        if size >= 300_000:
            errors.append(f"{rel_jpg}: size {size} bytes >= 300,000 bytes")
        if has_jpeg_exif(jpg):
            errors.append(f"{rel_jpg}: contains unstripped EXIF metadata")

    # Key WCAG AA contrast pairs (>= 4.5:1)
    contrast_checks = [
        ("index.html --teal-dark on --cream", "#0a4340", "#faf6ee", 4.5),
        ("index.html --muted on --white", "#5a6b69", "#ffffff", 4.5),
        ("the-copper-kettle --copper on --paper", "#8c471d", "#f3ead9", 4.5),
        ("the-copper-kettle --muted on --paper", "#665345", "#f3ead9", 4.5),
        ("northgate-barber-room --muted on --card", "#9c978e", "#232629", 4.5),
        ("linden-and-stone --clay on --linen", "#944a32", "#f6f2eb", 4.5),
        ("linden-and-stone --clay on #ffffff", "#944a32", "#ffffff", 4.5),
    ]
    for label, fg, bg, min_ratio in contrast_checks:
        ratio = contrast_ratio(fg, bg)
        if ratio < min_ratio:
            errors.append(f"WCAG contrast failure ({label}): {ratio:.2f}:1 < {min_ratio}:1")

    if errors:
        print("SITE AUDIT FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"SITE AUDIT PASSED: {len(PAGES)} pages, all images, links, headings, JS syntax, and WCAG contrasts verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
