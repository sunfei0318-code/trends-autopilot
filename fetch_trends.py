#!/usr/bin/env python3
"""Fetch overseas tech/startup trending items. Keyless sources only.

Sources (free, no API key -- verified Sep 2026):
  * Hacker News   - Algolia HN API (official), one call returns full fields
  * Google News   - news.google.com/rss, topic + keyword feeds
  * TechCrunch    - techcrunch.com/feed/ (RSS fallback for the news group)
  * GitHub        - search/repositories, recently created + star-sorted
  * dev.to        - public articles endpoint

Every source is independently guarded: a blocked or failing source yields an
empty list and the rest of the run continues. This matters because some hosts
are unreachable from restricted networks (e.g. api.github.com from an internal
sandbox) but work fine on GitHub Actions.
"""
import datetime
import json
import os
import urllib.parse
import xml.etree.ElementTree as ET

import requests

UA = {"User-Agent": "trends-bot/1.0 (+https://sun-pro.wasmer.app)"}
TIMEOUT = 30
# relative by default so it works from a repo checkout or GitHub Actions
OUT = os.environ.get("TRENDS_DATA", "trends_data.json")


def _rss(url, source_name, limit, tag=None):
    """Parse an RSS feed into the common item shape."""
    try:
        r = requests.get(url, headers=UA, timeout=TIMEOUT)
        root = ET.fromstring(r.content)
    except Exception as e:
        print(f"    ! {source_name} failed: {type(e).__name__}")
        return []

    out = []
    for item in root.iterfind(".//item"):
        if len(out) >= limit:
            break
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        out.append({
            "title": title,
            "url": link,
            "score": 0,
            "comments": 0,
            "source": source_name,
            "tag": tag or "",
            "ts": 0,
        })
    return out


# --------------------------------------------------------------------------- #
def fetch_hn(limit=20):
    """Hacker News front page via the official Algolia API (no key)."""
    try:
        r = requests.get("https://hn.algolia.com/api/v1/search",
                         params={"tags": "front_page", "hitsPerPage": limit},
                         headers=UA, timeout=TIMEOUT)
        hits = r.json().get("hits", [])
    except Exception as e:
        print(f"    ! hn failed: {type(e).__name__}")
        return []

    out = []
    for h in hits:
        oid = h.get("objectID")
        url = h.get("url") or f"https://news.ycombinator.com/item?id={oid}"
        title = h.get("title") or h.get("story_title") or ""
        if not title:
            continue
        out.append({
            "title": title,
            "url": url,
            "score": h.get("points", 0) or 0,
            "comments": h.get("num_comments", 0) or 0,
            "source": "Hacker News",
            "tag": "",
            "ts": 0,
        })
    return out


def fetch_gnews(limit=16):
    feeds = [("Technology", "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY"
                            "?hl=en-US&gl=US&ceid=US:en")]
    for kw in ("AI", "startup"):
        feeds.append((kw, "https://news.google.com/rss/search?q="
                          + urllib.parse.quote(kw) + "&hl=en-US&gl=US&ceid=US:en"))

    out, seen = [], set()
    per = max(1, limit // len(feeds))
    for label, url in feeds:
        items = _rss(url, "Google News", per, tag=label)
        for it in items:
            if it["title"] in seen:
                continue
            seen.add(it["title"])
            out.append(it)
    return out[:limit]


def fetch_techcrunch(limit=10):
    return _rss("https://techcrunch.com/feed/", "TechCrunch", limit)


def fetch_github(limit=12):
    since = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    try:
        r = requests.get("https://api.github.com/search/repositories",
                         params={"q": f"created:>{since} stars:>300",
                                 "sort": "stars", "order": "desc", "per_page": limit},
                         headers={**UA, "Accept": "application/vnd.github+json"},
                         timeout=TIMEOUT)
        items = r.json().get("items", [])
    except Exception as e:
        print(f"    ! github failed: {type(e).__name__}")
        return []

    out = []
    for it in items:
        out.append({
            "title": it.get("full_name", ""),
            "url": it.get("html_url", ""),
            "desc": (it.get("description") or "")[:150],
            "score": it.get("stargazers_count", 0) or 0,
            "comments": 0,
            "lang": it.get("language") or "",
            "source": "GitHub",
            "tag": "",
            "ts": 0,
        })
    return out


def fetch_devto(limit=10):
    try:
        r = requests.get("https://dev.to/api/articles",
                         params={"per_page": limit, "top": "1"},
                         headers=UA, timeout=TIMEOUT)
        arts = r.json()
    except Exception as e:
        print(f"    ! devto failed: {type(e).__name__}")
        return []

    return [{
        "title": a.get("title", ""),
        "url": a.get("url", ""),
        "desc": "",
        "score": a.get("public_reactions_count", 0) or 0,
        "comments": a.get("comments_count", 0) or 0,
        "lang": "",
        "source": "dev.to",
        "tag": "",
        "ts": 0,
    } for a in arts if a.get("title")]


# --------------------------------------------------------------------------- #
def main():
    print("fetching trends...")
    print("  hacker news (algolia)")
    hn = fetch_hn(20)
    print("  google news")
    gnews = fetch_gnews(16)
    print("  techcrunch")
    tc = fetch_techcrunch(10)
    print("  github")
    gh = fetch_github(12)
    print("  dev.to")
    dev = fetch_devto(10)

    # news group = Google News + TechCrunch fallback, Google first
    news, seen = [], set()
    for it in gnews + tc:
        if it["title"] in seen:
            continue
        seen.add(it["title"])
        news.append(it)

    data = {
        "fetched_at": datetime.datetime.now(datetime.timezone.utc)
                      .isoformat(timespec="seconds").replace("+00:00", "Z"),
        "groups": {"hn": hn, "news": news, "github": gh, "devto": dev},
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nsummary -> {OUT}")
    total = 0
    for k, v in data["groups"].items():
        print(f"  {k:8s} {len(v):3d} items")
        total += len(v)
    print(f"  {'TOTAL':8s} {total:3d} items")

    for k, v in data["groups"].items():
        if v:
            s = v[0]
            print(f"  first {k}: {s['title'][:64]} | {s['source']} | {s['score']}")


if __name__ == "__main__":
    main()
