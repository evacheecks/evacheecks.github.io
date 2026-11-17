#!/usr/bin/env python3
"""
Read-only inbound lead monitor for Reddit RSS/JSON feeds (r/forhire, r/smallbusiness,
r/excel, r/restaurateur, r/Barbershop).
Strictly read-only: never posts, comments, or sends messages.
Filters for [Hiring] or help-request posts matching Eva Cheeks' two tracks:
  1. One-page websites for restaurants, cafes, salons, and barbershops ($50-$120)
  2. ACCA/CFA B2B Excel COGS, bookkeeping, cash ledger, or commission trackers ($35-$125)
"""
import argparse
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SUBREDDITS = ["forhire", "excel", "smallbusiness", "restaurateur"]
KEYWORDS_WEB = re.compile(r"\b(website|landing page|one[- ]page|menu page|restaurant site|cafe site|salon site|barber)\b", re.I)
KEYWORDS_FIN = re.compile(r"\b(excel|spreadsheet|google sheet|bookkeeping|cogs|recipe cost|cash flow|ledger|commission tracker|financial model)\b", re.I)
HIRING_TAG = re.compile(r"\[hiring\]|looking for|need help with|anyone build|recommend a", re.I)
FORBID_TAG = re.compile(r"^\[for hire\]", re.I)


def fetch_subreddit(sub: str, limit: int = 25) -> list:
    url = f"https://www.reddit.com/r/{sub}/new.json?limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "EvaCheeksLeadMonitor/1.0 (read-only)"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return [c["data"] for c in data.get("data", {}).get("children", [])]
    except Exception as e:
        return [{"_error": f"r/{sub}: {e}"}]


def main():
    ap = argparse.ArgumentParser(description="Read-only inbound lead watcher for Reddit feeds.")
    ap.add_argument("--out", default="", help="Optional markdown output file")
    args = ap.parse_args()

    matches = []
    errors = []
    for sub in SUBREDDITS:
        posts = fetch_subreddit(sub)
        for p in posts:
            if "_error" in p:
                errors.append(p["_error"])
                continue
            title = p.get("title", "")
            selftext = p.get("selftext", "")
            if FORBID_TAG.search(title):
                continue
            blob = f"{title}\n{selftext}"
            track = None
            if KEYWORDS_WEB.search(blob) and (sub != "forhire" or HIRING_TAG.search(blob)):
                track = "Web ($50-$120)"
            elif KEYWORDS_FIN.search(blob) and (sub != "forhire" or HIRING_TAG.search(blob)):
                track = "Excel/Finance ($35-$125)"
            if track:
                created = datetime.fromtimestamp(p.get("created_utc", 0), tz=timezone.utc).strftime("%Y-%m-%d %H:%MZ")
                matches.append({
                    "subreddit": f"r/{sub}",
                    "track": track,
                    "title": title.replace("|", "/"),
                    "url": f"https://www.reddit.com{p.get('permalink', '')}",
                    "created": created,
                })

    lines = [
        "# Inbound Lead Digest (Read-Only)",
        f"- **Scanned (UTC)**: `{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}`",
        f"- **Matches Found**: `{len(matches)}`",
        "",
        "| Subreddit | Track | Created (UTC) | Title | URL |",
        "|---|---|---|---|---|",
    ]
    for m in matches:
        lines.append(f"| `{m['subreddit']}` | **{m['track']}** | `{m['created']}` | {m['title'][:80]} | {m['url']} |")
    if errors:
        lines.extend(["", "## Feed Notes", *[f"- {e}" for e in errors]])

    out_text = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).write_text(out_text, encoding="utf-8")
        print(f"Wrote digest ({len(matches)} matches) to {args.out}")
    else:
        print(out_text)


if __name__ == "__main__":
    main()
