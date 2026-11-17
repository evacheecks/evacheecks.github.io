#!/usr/bin/env python3
"""
Email-ready prospect finder & formatter for Eva Cheeks outreach.

Finds or validates newly opened local businesses (cafes, bakeries, restaurants,
barbershops, hair/nail salons, spas) that publish an email address on their own
public page/post and do NOT already have a custom priced website or priced POS /
booking storefront.

Outputs in Claude's exact plain-text format:
  NAME | TOWN/COUNTRY | TYPE | ROUTE | SOURCE | DEMO | NOTE

Modes:
  1. --from-json <path>  Validate, deduplicate, and format candidates collected
                         from search/browse tools into Antigravity-Prospects-*.txt.
  2. --discover          Run live web queries (DuckDuckGo HTML) for newly opened
                         businesses with "@gmail.com" / "email" in public posts,
                         fetch candidate pages, extract verified emails, and
                         apply all qualification gates.
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
    "squareup.com",
    "square.site",
    "booksy.com",
    "vagaro.com",
    "glossgenius.com",
    "fresha.com",
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


def strip_html(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def extract_valid_emails(text: str) -> list[str]:
    found = []
    seen = set()
    for m in EMAIL_RE.findall(text or ""):
        em = m.lower().rstrip(".,;:)")
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

    combined_text = f"{page_text} {source_url.lower()} {note.lower()}"
    for d in disq_domains:
        if d in combined_text:
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
            emails = extract_valid_emails(text)
            if not emails:
                continue
            title = re.split(r"\s+[|\-–—]\s+", hit["title"])[0].strip()
            candidates.append(
                {
                    "name": title or hit["title"][:60],
                    "location": "Town/Country to confirm",
                    "type": "local business",
                    "email": emails[0],
                    "source_url": url,
                    "source_label": "published on fetched page",
                    "note": f"discovered via query; verify opening date & menu status",
                    "page_text": text[:4000],
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
        help="Run live DuckDuckGo discovery queries for newly opened businesses with published emails",
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
        queries = args.queries or DEFAULT_QUERIES
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
