#!/usr/bin/env python3
"""Weekly freelance-lead collector (runs in GitHub Actions).

Sources (no API keys needed):
  1. Hacker News -- latest monthly "Ask HN: Who is hiring?" thread comments
     mentioning freelance/contract work in web or AI-infra, plus recent
     "Ask HN" freelancer-seeking posts (via public Algolia + Firebase APIs).
  2. Funding news -- AI startups that raised seed / Series A in the last
     30 days (TechCrunch RSS feeds).

Output:
  freelance-leads/data/latest.json
  freelance-leads/data/history/<run-date-PT>.json

Scoring / dedup / reporting stay on the Muse side (see SCAN-PLAYBOOK.md
in the agent workspace); this script only collects and normalizes.
"""
import json
import os
import re
import html
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "data")

FREELANCE_PATS = [r"freelanc\w*", r"\bcontract\b", r"\bcontractor\b",
                  r"contract-to-hire", r"\bgig\b"]
WEB_PATS = [r"react", r"next\.?js", r"\bwebsite\b", r"web\s?dev",
            r"frontend", r"front-end", r"full.?stack", r"\bweb\b", r"wordpress",
            r"landing page"]
AI_PATS = [r"\bllm\b", r"\brag\b", r"\bagent\b", r"mlops", r"machine learning",
           r"artificial intelligence", r"\bai\b", r"\bgpt\b", r"inference",
           r"fine-?tun\w*", r"foundation model", r"\bgenai\b", r"langchain",
           r"vector db", r"kubernetes", r"\bk8s\b"]
FUNDING_PATS = [r"\brais\w*\b", r"\bseed\b", r"series [ab]", r"\bfunding\b",
                r"lands \$", r"secures \$", r"closes \$", r"bags \$"]


def fetch_json(url, timeout=25):
    req = urllib.request.Request(
        url, headers={"User-Agent": "daily-pipeline-bot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def any_match(pats, text):
    return [p for p in pats if re.search(p, text, re.IGNORECASE)]


def strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


# ---------------- Hacker News ----------------

def hn_who_is_hiring():
    q = urllib.parse.quote("Ask HN: Who is hiring?")
    data = fetch_json(
        "https://hn.algolia.com/api/v1/search_by_date"
        f"?query={q}&tags=story&hitsPerPage=15")
    cands = [h for h in data.get("hits", [])
             if (h.get("title") or "").startswith("Ask HN: Who is hiring? (")]
    if not cands:
        # fall back: any "Ask HN: Who is hiring" title, newest first
        cands = [h for h in data.get("hits", [])
                 if (h.get("title") or "").startswith("Ask HN: Who is hiring")]
    if not cands:
        print("HN: no Who-is-hiring thread found")
        return []
    story = max(cands, key=lambda h: h["created_at_i"])
    sid = story["objectID"]
    print(f"HN: thread '{story['title']}' id={sid}")
    item = fetch_json(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json")
    kids = item.get("kids") or []
    print(f"HN: {len(kids)} comments to scan")

    def check(kid):
        try:
            c = fetch_json(
                f"https://hacker-news.firebaseio.com/v0/item/{kid}.json")
        except Exception:
            return None
        text = strip_html(c.get("text"))
        if not text:
            return None
        low = text.lower()
        if not any_match(FREELANCE_PATS, low):
            return None
        cats = []
        if any_match(AI_PATS, low):
            cats.append("ai-infra")
        if any_match(WEB_PATS, low):
            cats.append("web-dev")
        if not cats:
            return None
        return {
            "title": text[:140],
            "url": f"https://news.ycombinator.com/item?id={kid}",
            "source": "hn",
            "company_or_poster": c.get("by", ""),
            "published_at": datetime.fromtimestamp(
                c.get("time", 0), tz=timezone.utc).isoformat(),
            "snippet": text[:600],
            "categories": cats,
            "signal": "direct-ask",
        }

    leads = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        for r in ex.map(check, kids):
            if r:
                leads.append(r)
    print(f"HN: {len(leads)} freelance leads from Who-is-hiring")
    return leads


def hn_ask_freelancer():
    q = urllib.parse.quote("freelancer")
    data = fetch_json(
        f"https://hn.algolia.com/api/v1/search?query={q}&tags=ask_hn"
        f"&hitsPerPage=40")
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    leads = []
    for h in data.get("hits", [])[:25]:
        created = datetime.fromtimestamp(h["created_at_i"], tz=timezone.utc)
        if created < cutoff:
            continue
        title = h.get("title") or ""
        if not any_match([r"hir\w*", r"seek\w*", r"freelanc\w*", r"contract"],
                         title):
            continue
        low = title.lower()
        cats = []
        if any_match(AI_PATS, low):
            cats.append("ai-infra")
        if any_match(WEB_PATS, low):
            cats.append("web-dev")
        leads.append({
            "title": title,
            "url": h.get("url")
            or f"https://news.ycombinator.com/item?id={h['objectID']}",
            "source": "hn",
            "company_or_poster": h.get("author", ""),
            "published_at": created.isoformat(),
            "snippet": title,
            "categories": cats or ["web-dev"],
            "signal": "direct-ask",
        })
    print(f"HN: {len(leads)} Ask-HN freelancer posts")
    return leads


# ---------------- Funding news (RSS) ----------------

def funding_news():
    import feedparser
    feeds = [
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://techcrunch.com/category/startups/feed/",
    ]
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    leads, seen = [], set()
    for feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)
        except Exception as e:
            print(f"RSS failed {feed_url}: {e}")
            continue
        for e in feed.entries:
            link = (e.get("link") or "").split("?")[0]
            if not link or link in seen:
                continue
            seen.add(link)
            pub = e.get("published_parsed")
            if not pub:
                continue
            pub_dt = datetime(*pub[:6], tzinfo=timezone.utc)
            if pub_dt < cutoff:
                continue
            text = f"{e.get('title', '')} {strip_html(e.get('summary', ''))}"
            if not any_match(FUNDING_PATS, text):
                continue
            if not any_match(AI_PATS, text):
                continue
            leads.append({
                "title": e.get("title", "")[:180],
                "url": link,
                "source": "funding",
                "company_or_poster": "",
                "published_at": pub_dt.isoformat(),
                "snippet": strip_html(e.get("summary", ""))[:500],
                "categories": ["ai-infra"],
                "signal": "funding-news",
            })
    print(f"Funding: {len(leads)} AI funding items (30d)")
    return leads


# ---------------- main ----------------

def main():
    now_pt = datetime.now(PT)
    run_date = now_pt.strftime("%Y-%m-%d")
    items = []
    try:
        items += hn_who_is_hiring()
    except Exception as e:
        print(f"HN who-is-hiring FAILED: {e}")
    try:
        items += hn_ask_freelancer()
    except Exception as e:
        print(f"HN ask-freelancer FAILED: {e}")
    try:
        items += funding_news()
    except Exception as e:
        print(f"Funding FAILED: {e}")

    for i, it in enumerate(items, 1):
        it["id"] = f"pipe-{run_date}-{i:03d}"
        it.setdefault("contact", "")
        it.setdefault("found_date", run_date)
        it.setdefault("status", "new")

    payload = {
        "generated_at": now_pt.isoformat(),
        "run_date": run_date,
        "sources": ["hn", "funding"],
        "count": len(items),
        "items": items,
    }
    hist_dir = os.path.join(DATA_DIR, "history")
    os.makedirs(hist_dir, exist_ok=True)
    latest = os.path.join(DATA_DIR, "latest.json")
    hist = os.path.join(hist_dir, f"{run_date}.json")
    with open(latest, "w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    with open(hist, "w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"WROTE {latest} + {hist} ({len(items)} items)")


if __name__ == "__main__":
    main()
