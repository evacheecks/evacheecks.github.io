#!/usr/bin/env python3
"""
Deterministic prospect verification & deduplication CLI for Eva Cheeks outreach.
Reads a Claude-Prospects-YYYY-MM-DD-PLAIN.txt file (or JSON/CSV), cross-checks each
prospect against:
  1. Historical CRM records (normalized business name, email, IG handle, FB URL)
  2. Third-party priced POS / booking storefront gate (Toast, Square, KwickPOS/kwickmenu,
     Hotplate, Booksy, Vagaro, GlossGenius, Fresha, Clover, ChowNow)
  3. Email syntax & domain DNS resolution
  4. Vertical-to-demo URL mapping from outreach-config.json
Outputs a structured Markdown verification report (Antigravity-Checks-YYYY-MM-DD.md).
"""
import argparse
import csv
import json
import re
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "outreach-config.json"


def norm_name(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"&", " and ", s)
    s = re.sub(r"\b(the|cafe|café|coffee|restaurant|barbershop|barber|salon|spa|nail|nails|studio|room|shop|kitchen|bakery|llc|inc|ltd)\b", " ", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def norm_handle(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"^https?://(www\.)?instagram\.com/", "", s)
    s = s.strip("/").lstrip("@")
    return s.split("?")[0]


def check_domain_resolves(domain: str) -> bool:
    try:
        socket.getaddrinfo(domain, None)
        return True
    except Exception:
        return False


def pick_demo_url(vertical_text: str, config: dict) -> str:
    vt = (vertical_text or "").lower()
    demos = config.get("vertical_demos", {})
    if any(k in vt for k in ("salon", "nail", "spa", "hair", "lash", "brow", "beauty")):
        return demos.get("salon", "https://evacheecks.github.io/demo/linden-and-stone/")
    if any(k in vt for k in ("barber", "fade", "shave", "grooming")):
        return demos.get("barber", "https://evacheecks.github.io/demo/northgate-barber-room/")
    if any(k in vt for k in ("grill", "bbq", "kebab", "steak", "dinner", "bistro", "kitchen", "restaurant")):
        return demos.get("restaurant", "https://evacheecks.github.io/demo/saffron-and-salt/")
    if any(k in vt for k in ("tea", "brunch", "kettle", "pub")):
        return demos.get("brunch", "https://evacheecks.github.io/demo/the-copper-kettle/")
    return demos.get("cafe", "https://evacheecks.github.io/demo/harbor-street-coffee/")


def load_crm_index(crm_csv_path: Path):
    by_name = {}
    by_email = {}
    by_handle = {}
    if not crm_csv_path or not crm_csv_path.exists():
        return by_name, by_email, by_handle
    with crm_csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            bname = norm_name(row.get("Business_Name", ""))
            if bname:
                by_name[bname] = row
            em = (row.get("Email", "") or "").strip().lower()
            if em and "@" in em:
                by_email[em] = row
            ig = norm_handle(row.get("IG_or_FB_Handle", ""))
            if ig:
                by_handle[ig] = row
    return by_name, by_email, by_handle


def parse_plain_prospects(text: str):
    """Parse numbered or pipe-delimited prospect rows from Claude-Prospects-YYYY-MM-DD-PLAIN.txt."""
    prospects = []
    # Check for pipe-delimited lines first
    idx = 0
    for line in text.splitlines():
        line_s = line.strip()
        if "|" in line_s and not line_s.startswith(("#", "|")):
            parts = [p.strip() for p in line_s.split("|")]
            if len(parts) >= 3:
                idx += 1
                name = parts[0]
                subtitle = parts[1]
                emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", line_s)
                igs = re.findall(r"@([A-Za-z0-9._]{3,30})", line_s)
                urls = re.findall(r"https?://[^\s)\]>\"']+|(?:[a-z0-9-]+\.)+(?:kwickmenu|toasttab|square|booksy|vagaro|glossgenius|fresha|hotplate)\.[a-z]{2,}[^\s)\]>\"']*", line_s, re.I)
                prospects.append({
                    "index": idx,
                    "name": name,
                    "subtitle": subtitle,
                    "emails": [e.lower() for e in emails if not e.lower().endswith("evacheecks@gmail.com")],
                    "handles": igs,
                    "urls": urls,
                    "raw": line_s,
                })
    if prospects:
        return prospects

    blocks = re.split(r"\n(?=\d+\.\s+)", "\n" + text)
    for b in blocks:
        b = b.strip()
        m = re.match(r"^(\d+)\.\s+([^\n—–-]+?)(?:\s*[—–-]\s*([^\n]+))?\n(.*)$", b, re.S)
        if not m:
            continue
        num, name, subtitle, body = m.group(1), m.group(2).strip(), (m.group(3) or "").strip(), m.group(4)
        if name.upper().startswith(("SKIPPED", "SUMMARY", "NOTES", "RULE")):
            continue
        emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", body)
        igs = re.findall(r"@([A-Za-z0-9._]{3,30})", body)
        urls = re.findall(r"https?://[^\s)\]>\"']+|(?:[a-z0-9-]+\.)+(?:kwickmenu|toasttab|square|booksy|vagaro|glossgenius|fresha|hotplate)\.[a-z]{2,}[^\s)\]>\"']*", body, re.I)
        prospects.append({
            "index": int(num),
            "name": name,
            "subtitle": subtitle,
            "emails": [e.lower() for e in emails if not e.lower().endswith("evacheecks@gmail.com")],
            "handles": igs,
            "urls": urls,
            "raw": b,
        })
    return prospects


def evaluate_prospect(p: dict, config: dict, crm_idx: tuple) -> dict:
    by_name, by_email, by_handle = crm_idx
    disq_domains = config.get("qualification_gate", {}).get("disqualify_if_priced_pos_or_booking_storefront", [])

    flags = []
    status = "QUALIFIED"

    # 1. CRM duplicate check
    nn = norm_name(p["name"])
    if nn in by_name:
        prev = by_name[nn]
        flags.append(f"DUPLICATE_BUSINESS_NAME: already in CRM ({prev.get('Business_Name')} · {prev.get('Channel')} · {prev.get('First_Touch_Date')} · {prev.get('Status')})")
        status = "DO_NOT_CONTACT_DUPLICATE"
    for em in p["emails"]:
        if em in by_email:
            prev = by_email[em]
            flags.append(f"DUPLICATE_EMAIL ({em}): already in CRM ({prev.get('Status')})")
            status = "DO_NOT_CONTACT_DUPLICATE"
        dom = em.split("@", 1)[-1]
        if not check_domain_resolves(dom):
            flags.append(f"EMAIL_DOMAIN_DNS_FAIL: {dom} did not resolve")
            if status == "QUALIFIED":
                status = "HOLD_BAD_EMAIL"
    for h in p["handles"]:
        nh = norm_handle(h)
        if nh in by_handle:
            prev = by_handle[nh]
            flags.append(f"DUPLICATE_HANDLE (@{nh}): already in CRM ({prev.get('Status')})")
            status = "DO_NOT_CONTACT_DUPLICATE"

    # 2. POS / Booking storefront check
    raw_lower = p["raw"].lower()
    for d in disq_domains:
        if d in raw_lower:
            flags.append(f"PRICED_POS_OR_BOOKING_STOREFRONT: mentions `{d}` (verify if full priced menu/services are already live)")
            if status == "QUALIFIED":
                status = "REVIEW_POS_OR_BOOKING_LINK"

    if re.search(r"booking link in bio|online booking|kwickpos|kwickmenu|booksy|vagaro|glossgenius|fresha", raw_lower):
        if status == "QUALIFIED":
            status = "REVIEW_POS_OR_BOOKING_LINK"
        flags.append("BIO_BOOKING_OR_POS_DETECTED: prospect already has an online booking or POS menu link")

    demo_url = pick_demo_url(p["name"] + " " + p["subtitle"] + " " + p["raw"], config)
    return {
        **p,
        "status": status,
        "flags": flags,
        "recommended_demo": demo_url,
    }


def main():
    ap = argparse.ArgumentParser(description="Verify & deduplicate Claude prospect files.")
    ap.add_argument("inputs", nargs="+", help="Paths to Claude-Prospects-*-PLAIN.txt files")
    ap.add_argument("--crm", default=str(ROOT / "crm" / "outreach_crm_seed.csv"), help="Path to CRM CSV")
    ap.add_argument("--out", default="", help="Output markdown report path")
    args = ap.parse_args()

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    crm_idx = load_crm_index(Path(args.crm) if args.crm else None)

    lines = [
        f"# Antigravity Prospect Verification Report",
        f"- **Generated (UTC)**: `{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}`",
        f"- **Config Version**: `{config.get('version')}`",
        "",
    ]

    for inp in args.inputs:
        path = Path(inp)
        text = path.read_text(encoding="utf-8")
        prospects = parse_plain_prospects(text)
        lines.append(f"## File: `{path.name}` ({len(prospects)} numbered prospects parsed)")
        lines.append("")
        lines.append("| # | Business | Subtitle / City | Status | Recommended Demo | Notes / Flags |")
        lines.append("|---|---|---|---|---|---|")
        for p in prospects:
            ev = evaluate_prospect(p, config, crm_idx)
            flag_str = "; ".join(ev["flags"]) if ev["flags"] else "Clean — no website or duplicate found"
            lines.append(
                f"| {ev['index']} | **{ev['name']}** | {ev['subtitle']} | `{ev['status']}` | {ev['recommended_demo']} | {flag_str} |"
            )
        lines.append("")

    report = "\n".join(lines) + "\n"
    if args.out:
        out_path = Path(args.out)
        out_path.write_text(report, encoding="utf-8")
        print(f"Wrote verification report to {out_path}")
    else:
        sys.stdout.write(report)


if __name__ == "__main__":
    main()
