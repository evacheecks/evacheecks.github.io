#!/usr/bin/env python3
"""
Email-ready prospect finder & formatter for Eva Cheeks outreach.

Finds or validates independent local businesses (cafes, bakeries, restaurants,
barbershops, hair/nail salons) — both newly opened and established no-website shops —
that publish an email address on their own public page/post and do NOT already have a
custom priced website or priced POS / booking storefront.

Outputs in plain-text format:
  NAME | TOWN/COUNTRY | TYPE | ROUTE | SOURCE | DEMO | NOTE

Modes:
  1. --from-json <path>  Validate, deduplicate, and format candidates collected
                         from search/browse tools into Antigravity-Prospects-*.txt.
  2. --discover          Run live DuckDuckGo queries (--mode new|established|both),
                         fetch candidate pages, decode CF-protected/escaped emails,
                         extract outbound URLs, and apply all qualification gates.
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify_prospects import (  # noqa: E402
    CONFIG_PATH,
    check_domain_resolves,
    domain_mentioned,
    load_crm_index,
    norm_handle,
    norm_name,
    pick_demo_url,
)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

EMAIL_RE = re.compile(r"\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")

IGNORED_EMAIL_DOMAINS = {
    "example.com",
    "domain.com",
    "email.com",
    "sentry.io",
    "wixpress.com",
    "squarespace.com",
    "godaddy.com",
    "wordpress.com",
    "facebook.com",
    "fb.com",
    "instagram.com",
    "google.com",
    "gstatic.com",
    "yelp.com",
    "tripadvisor.com",
    "toasttab.com",
    "toast.app",
    "squareup.com",
    "square.site",
    "squareup.site",
    "booksy.com",
    "vagaro.com",
    "glossgenius.com",
    "fresha.com",
    "setmore.com",
    "gettimely.com",
    "timely.com",
    "styleseat.com",
    "schedulicity.com",
    "acuityscheduling.com",
    "simplybook.me",
    "simplybook.net",
    "phorest.com",
    "getsquire.com",
    "squire.com",
    "sumup.com",
    "sumupbookings.com",
    "bakesy.shop",
    "mailchimp.com",
    "constantcontact.com",
    "cloudflare.com",
    "linktree.com",
    "linktr.ee",
    "beacons.ai",
    "carrd.co",
    "bio.site",
}

IGNORED_EMAIL_LOCAL_PREFIXES = (
    "noreply",
    "no-reply",
    "donotreply",
    "support@",
    "privacy@",
    "abuse@",
    "postmaster@",
    "webmaster@",
    "evacheecks@",
)

AGGREGATOR_HOSTS = (
    "yelp.com",
    "tripadvisor.com",
    "mapquest.com",
    "yellowpages.com",
    "bbb.org",
    "linkedin.com",
    "indeed.com",
    "glassdoor.com",
    "reddit.com",
    "pinterest.com",
    "tiktok.com",
    "youtube.com",
)

DEMO_SHORT_LABELS = {
    "harbor-street-coffee": "Harbor Street",
    "the-copper-kettle": "Copper Kettle",
    "saffron-and-salt": "Saffron & Salt",
    "northgate-barber-room": "Northgate Barber",
    "linden-and-stone": "Linden & Stone",
}

DEFAULT_QUERIES = [
    '"grand opening" ("cafe" OR "coffee" OR "bakery") "@gmail.com" -site:yelp.com',
    '"now open" ("barbershop" OR "hair salon" OR "nail salon") "@gmail.com" -site:yelp.com',
    '"soft opening" ("restaurant" OR "bistro" OR "kitchen") "@gmail.com" -site:yelp.com',
    '"newly opened" ("salon" OR "cafe" OR "bakery") ("email" OR "@gmail.com") -site:yelp.com',
]

ESTABLISHED_QUERIES = [
    'site:linktr.ee ("barbershop" OR "hair salon" OR "nail salon") "@gmail.com"',
    'site:linktr.ee ("cafe" OR "bakery" OR "restaurant") "@gmail.com" -site:linktree.com',
    'site:carrd.co ("barber" OR "cafe" OR "restaurant" OR "bakery" OR "nails") "@gmail.com"',
    'site:beacons.ai ("nails" OR "salon" OR "barbershop" OR "cafe") "@gmail.com"',
    'site:bio.site ("cafe" OR "bakery" OR "restaurant" OR "salon") "@gmail.com"',
]

STATIC_ASSET_HOST_PARTS = (
    "w3.org",
    "schema.org",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "googletagmanager.com",
    "google-analytics.com",
    "onetrust.com",
    "cookiebot.com",
    "datagrail.io",
    "unpkg.com",
    "cloudflare.com",
    "ugc.production.linktr.ee",
    "assets.production.linktr.ee",
)


def short_demo_label(demo_url: str) -> str:
    for slug, label in DEMO_SHORT_LABELS.items():
        if slug in demo_url:
            return label
    return demo_url


def fetch_url(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        ctype = resp.headers.get("Content-Type", "")
        if "text" not in ctype and "html" not in ctype and "json" not in ctype and ctype:
            return ""
        raw = resp.read(512_000)
        return raw.decode("utf-8", errors="replace")


def decode_cfemails(html: str) -> list[str]:
    """Decode Cloudflare email protection hex strings (data-cfemail)."""
    decoded = []
    for hx in re.findall(r'data-cfemail="([0-9a-fA-F]+)"', html or ""):
        try:
            raw = bytes.fromhex(hx)
            if len(raw) < 2:
                continue
            key = raw[0]
            em = "".join(chr(b ^ key) for b in raw[1:]).strip().lower()
            if "@" in em:
                decoded.append(em)
        except Exception:
            continue
    return decoded


def normalize_embedded_escapes(text: str) -> str:
    """Unescape JSON/JS string escapes before regex scanning (e.g. Linktree __NEXT_DATA__)."""
    if not text:
        return ""
    s = (
        text.replace("\\u002F", "/")
        .replace("\\u002f", "/")
        .replace("\\/", "/")
        .replace("\\u0040", "@")
        .replace("\\n", " ")
        .replace("\\r", " ")
        .replace("\\t", " ")
    )
    return unescape(s)


def strip_html(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def extract_outbound_urls(html: str, source_url: str = "") -> list[str]:
    """Extract outbound http(s) URLs from anchors and hydrated JSON payloads (ignoring static assets)."""
    if not html:
        return []
    norm = normalize_embedded_escapes(html)
    src_host = urllib.parse.urlparse(source_url).netloc.lower() if source_url else ""
    raw_urls = []
    raw_urls.extend(re.findall(r'href=["\'](https?://[^"\'\s<>]+)["\']', norm, flags=re.I))
    raw_urls.extend(re.findall(r'"url"\s*:\s*"(https?://[^"\s<>]+)"', norm, flags=re.I))

    seen = set()
    outbound = []
    for u in raw_urls:
        u = u.rstrip(").,;")
        parsed = urllib.parse.urlparse(u)
        host = parsed.netloc.lower()
        path_l = parsed.path.lower()
        if not host or (src_host and host == src_host):
            continue
        if any(part in host for part in STATIC_ASSET_HOST_PARTS):
            continue
        if path_l.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js", ".woff2", ".ico")):
            continue
        if u not in seen:
            seen.add(u)
            outbound.append(u)
    return outbound


def extract_valid_emails(text: str, extra_emails: list[str] | None = None) -> list[str]:
    found = []
    seen = set()
    norm = normalize_embedded_escapes(text or "").replace("mailto:", " ")
    candidates = list(EMAIL_RE.findall(norm)) + list(extra_emails or [])
    for m in candidates:
        em = m.strip().lower().rstrip(".,;:)")
        if em in seen:
            continue
        if any(em.startswith(p) for p in IGNORED_EMAIL_LOCAL_PREFIXES):
            continue
        dom = em.split("@", 1)[-1]
        if dom in IGNORED_EMAIL_DOMAINS:
            continue
        if dom.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js")):
            continue
        seen.add(em)
        found.append(em)
    return found


def search_duckduckgo(query: str, max_results: int = 8) -> list[dict]:
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query)
    html = fetch_url(url, timeout=15)
    results = []
    for m in re.finditer(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        html,
        flags=re.S | re.I,
    ):
        href = unescape(m.group(1))
        title = strip_html(m.group(2))
        if "uddg=" in href:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            href = qs.get("uddg", [href])[0]
        if not href.startswith("http"):
            continue
        host = urllib.parse.urlparse(href).netloc.lower()
        if any(agg in host for agg in AGGREGATOR_HOSTS):
            continue
        results.append({"title": title, "url": href})
        if len(results) >= max_results:
            break
    return results


def evaluate_candidate(cand: dict, config: dict, crm_idx: tuple) -> dict:
    by_name, by_email, by_handle = crm_idx
    disq_domains = config.get("qualification_gate", {}).get(
        "disqualify_if_priced_pos_or_booking_storefront", []
    )

    name = (cand.get("name") or "").strip()
    location = (cand.get("location") or "Town/Country to confirm").strip()
    btype = (cand.get("type") or "local business").strip()
    email = (cand.get("email") or "").strip().lower()
    ig_handle = (cand.get("ig_handle") or "").strip()
    source_url = (cand.get("source_url") or "").strip()
    source_label = (cand.get("source_label") or "own page/post").strip()
    note = (cand.get("note") or "").strip()
    page_text = (cand.get("page_text") or "").lower()
    outbound_urls = [str(u).strip().lower() for u in (cand.get("outbound_urls") or []) if u]

    reasons = []
    if not name:
        reasons.append("MISSING_NAME")
    if not email or "@" not in email:
        reasons.append("MISSING_EMAIL")
    if not source_url.startswith("http"):
        reasons.append("MISSING_SOURCE_URL")

    nn = norm_name(name)
    if nn and nn in by_name:
        prev = by_name[nn]
        reasons.append(f"DUPLICATE_CRM_NAME ({prev.get('Business_Name')})")

    if email and email in by_email:
        reasons.append("DUPLICATE_CRM_EMAIL")

    if ig_handle:
        nh = norm_handle(ig_handle)
        if nh and nh in by_handle:
            reasons.append(f"DUPLICATE_CRM_HANDLE (@{nh})")

    if email and "@" in email:
        dom = email.split("@", 1)[-1]
        if dom in IGNORED_EMAIL_DOMAINS:
            reasons.append(f"IGNORED_EMAIL_DOMAIN ({dom})")
        elif not check_domain_resolves(dom):
            reasons.append(f"EMAIL_DOMAIN_DNS_FAIL ({dom})")

    combined_text = f"{page_text} {source_url.lower()} {note.lower()} {' '.join(outbound_urls)}"
    for d in disq_domains:
        if domain_mentioned(d, combined_text):
            reasons.append(f"PRICED_POS_OR_BOOKING ({d})")

    demo_url = pick_demo_url(f"{name} {btype} {note}", config)
    demo_short = short_demo_label(demo_url)

    route = f"EMAIL {email} ({source_label})"
    if ig_handle:
        h = ig_handle if ig_handle.startswith("@") else f"@{ig_handle}"
        route += f", IG {h}"

    line = f"{name} | {location} | {btype} | {route} | {source_url} | {demo_short} | {note}"
    return {
        "qualified": len(reasons) == 0,
        "reasons": reasons,
        "line": line,
        "demo_url": demo_url,
        "candidate": cand,
    }


def discover_candidates(queries: list[str], max_per_query: int) -> list[dict]:
    candidates = []
    seen_urls = set()
    for q in queries:
        try:
            hits = search_duckduckgo(q, max_results=max_per_query)
        except Exception as exc:
            print(f"[warn] search failed for {q!r}: {exc}", file=sys.stderr)
            continue
        for hit in hits:
            url = hit["url"]
            if url in seen_urls:
                continue
            seen_urls.add(url)
            try:
                html = fetch_url(url, timeout=10)
            except Exception:
                continue
            text = strip_html(html)
            cf_emails = decode_cfemails(html)
            emails = extract_valid_emails(f"{text}\n{normalize_embedded_escapes(html)}", extra_emails=cf_emails)
            if not emails:
                continue
            outbound_urls = extract_outbound_urls(html, source_url=url)
            title = re.split(r"\s+[|\-–—]\s+", hit["title"])[0].strip()
            candidates.append(
                {
                    "name": title or hit["title"][:60],
                    "location": "Town/Country to confirm",
                    "type": "local business",
                    "email": emails[0],
                    "source_url": url,
                    "source_label": "CF-decoded/published on fetched page" if cf_emails and emails[0] in cf_emails else "published on fetched page",
                    "note": "discovered via query; verify brick-and-mortar shop, active operation & own-site/POS links",
                    "page_text": text[:4000],
                    "outbound_urls": outbound_urls,
                }
            )
            time.sleep(0.4)
    return candidates


def format_output(evaluated: list[dict], date_str: str, header_note: str = "") -> str:
    qualified = [e for e in evaluated if e["qualified"]]
    rejected = [e for e in evaluated if not e["qualified"]]
    now_utc = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")

    lines = [
        f"Antigravity-Prospects-{date_str} (plain text, one per line: NAME | TOWN/COUNTRY | TYPE | ROUTE | SOURCE | DEMO | NOTE)",
        f"Generated {now_utc}. {len(qualified)} PUBLISHED EMAILS verified against CRM, DNS, and POS/booking gates ({len(rejected)} filtered out).",
    ]
    if header_note:
        lines.append(header_note.strip())
    lines.append("")
    lines.append("== PUBLISHED EMAILS ==")
    if qualified:
        for item in qualified:
            lines.append(item["line"])
    else:
        lines.append("(No qualified published-email prospects in this run.)")

    if rejected:
        lines.append("")
        lines.append("== FILTERED OUT (DO NOT SEND) ==")
        for item in rejected:
            cname = item["candidate"].get("name", "Unknown")
            lines.append(f"- {cname}: {', '.join(item['reasons'])}")

    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(
        description="Find, verify, and format email-ready prospects for Eva Cheeks."
    )
    ap.add_argument("--from-json", help="Path to JSON array of candidate objects")
    ap.add_argument(
        "--discover",
        action="store_true",
        help="Run live DuckDuckGo discovery queries for businesses with published emails",
    )
    ap.add_argument(
        "--mode",
        choices=["new", "established", "both"],
        default="both",
        help="Discovery query mode: newly opened ('new'), established no-website link-in-bio ('established'), or 'both' (default)",
    )
    ap.add_argument(
        "--query",
        action="append",
        dest="queries",
        help="Custom search query (repeatable; used with --discover)",
    )
    ap.add_argument("--max-per-query", type=int, default=6)
    ap.add_argument("--crm", default=str(ROOT / "crm" / "outreach_crm_seed.csv"))
    ap.add_argument("--out", default="", help="Output .txt path (default: stdout)")
    ap.add_argument(
        "--date",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        help="Date string YYYY-MM-DD for file header",
    )
    ap.add_argument("--note", default="", help="Optional header note")
    args = ap.parse_args()

    if not args.from_json and not args.discover:
        ap.error("Specify --from-json <path> and/or --discover")

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    crm_idx = load_crm_index(Path(args.crm) if args.crm else None)

    candidates = []
    if args.from_json:
        raw = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw = raw.get("candidates", [])
        candidates.extend(raw)

    if args.discover:
        if args.queries:
            queries = args.queries
        elif args.mode == "new":
            queries = DEFAULT_QUERIES
        elif args.mode == "established":
            queries = ESTABLISHED_QUERIES
        else:
            queries = ESTABLISHED_QUERIES + DEFAULT_QUERIES
        candidates.extend(discover_candidates(queries, args.max_per_query))

    evaluated = [evaluate_candidate(c, config, crm_idx) for c in candidates]
    output = format_output(evaluated, args.date, args.note)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        q_count = sum(1 for e in evaluated if e["qualified"])
        print(f"Wrote {q_count} qualified email prospects to {out_path}")
    else:
        sys.stdout.write(output)


if __name__ == "__main__":
    main()
