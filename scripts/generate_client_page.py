#!/usr/bin/env python3
"""
Conditional Post-Reply Personalized Preview Generator (`p/<slug>/index.html`).
IMPORTANT: Run ONLY after a prospect replies positively to Template A/B/D and sends
their menu or service list, or when preparing an approved warm-lead mock-up.
Includes OpenGraph social preview tags (`og:title`, `og:description`, `og:image`,
`twitter:card`) so pasting `https://evacheecks.github.io/p/<slug>/` into Instagram,
Facebook, WhatsApp, or email unfurls a rich preview card.
"""
import argparse
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def render_page(spec: dict) -> str:
    name = html.escape(spec["business_name"])
    slug = spec.get("slug") or slugify(spec["business_name"])
    city = html.escape(spec.get("city", ""))
    tagline = html.escape(spec.get("tagline", f"Menu, hours, and location for {spec['business_name']}."))
    vertical = spec.get("vertical", "restaurant").lower()
    cta_label = html.escape(spec.get("cta_label", "Book / Order Now"))
    cta_url = html.escape(spec.get("cta_url", "#visit"))
    phone = html.escape(spec.get("phone", ""))
    address = html.escape(spec.get("address", city))
    hours = spec.get("hours", ["Mon–Sun: See counter or call to confirm"])
    sections = spec.get("sections", [])
    og_img = html.escape(spec.get("og_image", "https://evacheecks.github.io/demo/harbor-street-coffee/img/hero.jpg"))
    canonical = f"https://evacheecks.github.io/p/{slug}/"

    accent = "#0f5f5c"
    bg = "#faf6ee"
    if "salon" in vertical or "nail" in vertical or "spa" in vertical:
        accent = "#24362e"
        bg = "#f6f2eb"
    elif "barber" in vertical:
        accent = "#8c5a16"
        bg = "#f5f1e8"

    sec_html = []
    for sec in sections:
        sec_title = html.escape(sec.get("title", "Menu"))
        rows = []
        for item in sec.get("items", []):
            iname = html.escape(item.get("name", ""))
            idesc = html.escape(item.get("description", ""))
            iprice = html.escape(str(item.get("price", "")))
            desc_tag = f"<i>{idesc}</i>" if idesc else ""
            rows.append(f'<div class="row"><span><b>{iname}</b>{desc_tag}</span><span class="pr">{iprice}</span></div>')
        sec_html.append(f'<div class="cat"><h3>{sec_title}</h3>{"".join(rows)}</div>')

    hours_html = "".join(f"<p>{html.escape(h)}</p>" for h in hours)
    maps_q = html.escape(re.sub(r"\s+", "+", f"{spec['business_name']} {spec.get('city', '')}".strip()))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} · {city} (Draft Preview by Eva Cheeks)</title>
<meta name="description" content="{tagline}">
<meta name="robots" content="noindex">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{name} · {city} (One-Page Website Preview)">
<meta property="og:description" content="{tagline}">
<meta property="og:type" content="website">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{og_img}">
<meta name="twitter:card" content="summary_large_image">
<style>
  :root {{ --accent: {accent}; --bg: {bg}; --ink: #1d2422; --muted: #5b6461; --line: #dcd6ca; --card: #ffffff; }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; overflow-x: clip; background: var(--bg); color: var(--ink); font: 16px/1.6 system-ui, -apple-system, sans-serif; }}
  .note {{ font-size: 12px; text-align: center; padding: 8px 12px; background: var(--card); border-bottom: 1px solid var(--line); color: var(--muted); }}
  .note a {{ color: var(--accent); font-weight: 600; }}
  .hero {{ background: var(--accent); color: #fff; padding: 48px 20px 44px; }}
  .wrap {{ max-width: 860px; margin: 0 auto; padding: 0 20px; }}
  .kicker {{ text-transform: uppercase; letter-spacing: 2.5px; font-size: 12px; opacity: .85; margin: 0 0 8px; }}
  h1 {{ margin: 0 0 12px; font-size: clamp(2rem, 6vw, 3.2rem); line-height: 1.08; }}
  .sub {{ max-width: 42ch; opacity: .92; margin: 0 0 22px; font-size: 1.08rem; }}
  .btn {{ display: inline-block; padding: 12px 20px; border-radius: 999px; background: #fff; color: var(--accent); font-weight: 700; text-decoration: none; margin-right: 10px; }}
  section {{ padding: 36px 0 12px; }}
  h2 {{ margin: 0 0 12px; font-size: 1.6rem; color: var(--accent); border-bottom: 2px solid var(--accent); padding-bottom: 8px; }}
  .cat {{ padding: 14px 0; border-bottom: 1px solid var(--line); }}
  .cat h3 {{ margin: 0 0 8px; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 2px; color: var(--muted); }}
  .row {{ display: flex; justify-content: space-between; gap: 16px; padding: 7px 0; border-bottom: 1px dotted var(--line); }}
  .row:last-child {{ border-bottom: 0; }}
  .row i {{ display: block; font-style: normal; font-size: 0.88rem; color: var(--muted); }}
  .pr {{ font-weight: 700; white-space: nowrap; font-variant-numeric: tabular-nums; }}
  .visit {{ display: grid; gap: 20px; padding: 36px 0; }}
  .card {{ background: var(--card); border: 0; border-radius: 12px; padding: 20px; box-shadow: 0 2px 12px rgba(0,0,0,0.05); }}
  .card h3 {{ margin: 0 0 8px; color: var(--accent); font-size: 1rem; }}
  .card p {{ margin: 4px 0; }}
  footer {{ border-top: 1px solid var(--line); padding: 20px 0 40px; font-size: 0.85rem; color: var(--muted); }}
  @media (min-width: 720px) {{ .visit {{ grid-template-columns: 1fr 1fr; }} }}
</style>
</head>
<body>
<div class="note">Free draft preview prepared for <strong>{name}</strong> by Eva Cheeks · <a href="../../#contact">Confirm details or request changes</a></div>
<header class="hero">
  <div class="wrap">
    <p class="kicker">{city}</p>
    <h1>{name}</h1>
    <p class="sub">{tagline}</p>
    <a class="btn" href="{cta_url}">{cta_label}</a>
  </div>
</header>
<main class="wrap">
  <section id="menu">
    <h2>Menu &amp; Services</h2>
    {"".join(sec_html)}
  </section>
  <section class="visit" id="visit">
    <div class="card">
      <h3>Hours</h3>
      {hours_html}
    </div>
    <div class="card">
      <h3>Location &amp; Contact</h3>
      <p>{address}</p>
      {f'<p><a href="tel:{phone}">{phone}</a></p>' if phone else ''}
      <p><a href="https://www.google.com/maps/search/?api=1&amp;query={maps_q}">Open in Google Maps</a></p>
    </div>
  </section>
  <footer>Draft preview for {name}. Built by <a href="../../">Eva Cheeks</a>.</footer>
</main>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="Generate a personalized post-reply preview page under p/<slug>/index.html")
    ap.add_argument("spec_json", help="Path to prospect JSON spec file")
    args = ap.parse_args()

    spec = json.loads(Path(args.spec_json).read_text(encoding="utf-8"))
    slug = spec.get("slug") or slugify(spec["business_name"])
    out_dir = ROOT / "p" / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "index.html"
    out_file.write_text(render_page(spec), encoding="utf-8")
    print(f"Generated preview page: {out_file} -> https://evacheecks.github.io/p/{slug}/")


if __name__ == "__main__":
    main()
