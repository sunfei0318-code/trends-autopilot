#!/usr/bin/env python3
"""Render the fetched trends as a WordPress page and publish it to /trends/.

Reads   : trends_data.json  (produced by fetch_trends.py)
Writes  : the WP page with slug 'trends' (create if missing, update if present)
Auth    : Application Password (Basic auth) -- works headlessly, no browser

House rules honoured:
  * content wrapped in <!-- wp:html --> so wpautop cannot inject stray <br>/<p>
  * all text escaped; no inline <script> at all, so the WP '&' pitfall cannot bite
  * outbound links get rel="noopener nofollow" (we index headlines, we do not
    republish article text -- attribution stays with the source)
"""
import html
import json
import os
import sys

import requests

BASE = os.environ.get("WP_BASE", "https://sun-pro.wasmer.app")
DATA = os.environ.get("TRENDS_DATA", "trends_data.json")
SLUG = "trends"
TITLE = "Tech & Startup Trends"


def _auth():
    """WordPress 凭据，按优先级取：

    1. 环境变量 WP_APP_USER / WP_APP_PASS —— GitHub Actions 用 secrets 注入的路径
    2. 本脚本同目录下的 wp_app_password.txt —— 本地手动运行时的便捷方式
       （第 1 行用户名，第 2 行 Application Password）
    """
    u = os.environ.get("WP_APP_USER")
    p = os.environ.get("WP_APP_PASS")
    if u and p:
        return (u, p)

    here = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "wp_app_password.txt")
    if os.path.exists(here):
        with open(here, encoding="utf-8") as f:
            lines = [x.strip() for x in f if x.strip() and not x.startswith("#")]
        if len(lines) >= 2:
            return (lines[0], lines[1])

    raise SystemExit(
        "未找到 WordPress 凭据。请二选一：\n"
        "  * GitHub Actions：在仓库 Settings -> Secrets and variables -> Actions\n"
        "    添加 WP_APP_USER 和 WP_APP_PASS 两个 secret；\n"
        "  * 本地运行：export WP_APP_USER=... WP_APP_PASS=...，\n"
        "    或在本脚本同目录放 wp_app_password.txt（第 1 行用户名，第 2 行密码）。"
    )

CSS = """
<style>
.tr{max-width:880px!important;margin:0 auto!important;font-family:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif!important;color:#1f2937!important;line-height:1.7!important;font-size:16px!important}
.tr *{box-sizing:border-box!important}
.tr h2{font-size:22px!important;margin:34px 0 10px!important;color:#111827!important;line-height:1.35!important;font-weight:700!important}
.tr p{margin:10px 0!important;font-size:15.5px!important;color:#374151!important}
.tr-intro{background:#f8fafc!important;border:1px solid #e2e8f0!important;border-radius:16px!important;padding:20px 22px!important;margin:18px 0 26px!important}
.tr-sub{margin:0 0 12px!important;font-size:14px!important;color:#64748b!important}
.tr-list{display:flex!important;flex-direction:column!important;gap:9px!important;margin:12px 0 0!important}
.tr-item{display:flex!important;gap:12px!important;align-items:flex-start!important;background:#ffffff!important;border:1px solid #e5e7eb!important;border-radius:12px!important;padding:12px 15px!important;text-decoration:none!important;color:inherit!important;transition:border-color .15s,box-shadow .15s!important}
.tr-item:hover{border-color:#a5b4fc!important;box-shadow:0 4px 14px rgba(79,70,229,.10)!important}
.tr-num{flex:0 0 24px!important;font-size:13.5px!important;font-weight:700!important;color:#4338ca!important;text-align:right!important;padding-top:1px!important}
.tr-body{min-width:0!important}
.tr-title{display:block!important;font-size:15.5px!important;font-weight:600!important;color:#1e3a8a!important;line-height:1.5!important}
.tr-item:hover .tr-title{color:#4338ca!important;text-decoration:underline!important}
.tr-meta{display:block!important;font-size:12.5px!important;color:#64748b!important;margin-top:3px!important}
.tr-badge{display:inline-block!important;background:#eef2ff!important;color:#4338ca!important;border:1px solid #c7d2fe!important;border-radius:999px!important;padding:2px 9px!important;font-size:11.5px!important;font-weight:600!important}
.tr-empty{background:#f8fafc!important;border:1px dashed #cbd5e1!important;border-radius:12px!important;padding:14px 16px!important;font-size:14px!important;color:#64748b!important;margin:12px 0 0!important}
.tr-foot{margin-top:32px!important;padding-top:16px!important;border-top:1px solid #e5e7eb!important;font-size:14px!important;color:#64748b!important;line-height:1.8!important}
.tr-foot a{color:#4338ca!important;text-decoration:underline!important}
@media (max-width:600px){
  .tr{padding:0 4px!important}
  .tr-intro{padding:16px 14px!important}
  .tr-num{flex:0 0 18px!important}
  .tr-title{font-size:14.5px!important}
}
</style>
"""


def esc(s):
    return html.escape(str(s or ""), quote=True)


def num(n):
    try:
        return f"{int(n):,}"
    except Exception:
        return "0"


def meta_for(kind, it):
    bits = []
    src = it.get("source") or ""
    if src:
        bits.append(esc(src))
    if kind == "hn":
        bits.append(f"{num(it.get('score'))} points")
        bits.append(f"{num(it.get('comments'))} comments")
    elif kind == "github":
        bits.append(f"{num(it.get('score'))} stars")
        if it.get("lang"):
            bits.append(esc(it["lang"]))
    elif kind == "devto":
        bits.append(f"{num(it.get('score'))} reactions")
        bits.append(f"{num(it.get('comments'))} comments")
    return " &middot; ".join(bits)


def render_group(kind, heading, sub, items):
    if not items:
        return (f"<h2>{esc(heading)}</h2>\n"
                f'<div class="tr-empty">No items on this run. '
                f'This source refreshes automatically on the next scheduled fetch.</div>\n')

    rows = []
    for i, it in enumerate(items, 1):
        url = esc(it.get("url") or "")
        title = esc(it.get("title") or "")
        if not title or not url:
            continue
        desc = it.get("desc")
        desc_html = (f'<span class="tr-meta">{esc(desc)}</span>'
                     if desc else "")
        rows.append(
            f'<a class="tr-item" href="{url}" target="_blank" rel="noopener nofollow">'
            f'<span class="tr-num">{i}</span>'
            f'<span class="tr-body">'
            f'<span class="tr-title">{title}</span>'
            f'<span class="tr-meta">{meta_for(kind, it)}</span>'
            f"{desc_html}"
            f"</span></a>"
        )
    if not rows:
        return ""
    return (f"<h2>{esc(heading)}</h2>\n"
            f'<p class="tr-sub">{esc(sub)}</p>\n'
            f'<div class="tr-list">\n' + "\n".join(rows) + "\n</div>\n")


def build():
    with open(DATA, encoding="utf-8") as f:
        d = json.load(f)
    g = d["groups"]
    when = esc(d.get("fetched_at", ""))

    # The whole page is emitted as ONE wp:html block after the stylesheet.
    # That keeps wpautop away from the card markup (no stray <br>/<p> inside
    # .tr-list), while Gutenberg still renders the block as a tidy collapsed
    # card instead of spraying 200-odd raw lines into the editing canvas.
    body = [CSS, '<div class="tr">']
    body.append(
        '<p class="tr-intro">A running feed of what the overseas tech and startup '
        'internet is talking about, refreshed automatically from public sources. '
        'Every headline links back to the original publisher &mdash; nothing is '
        'republished here. Last updated <strong>' + when + '</strong>.</p>'
    )

    body.append(render_group(
        "hn", "Hacker News", "Highest-scoring front-page stories right now.", g.get("hn", [])))
    body.append(render_group(
        "news", "Tech &amp; Startup News",
        "Latest items from technology desks and startup coverage.", g.get("news", [])))
    body.append(render_group(
        "github", "Open Source on the Move",
        "Repositories created in the last 30 days, ranked by stars.", g.get("github", [])))
    body.append(render_group(
        "devto", "From Developers",
        "Most-reacted developer posts this week.", g.get("devto", [])))

    body.append(
        '<p class="tr-foot">Sources: Hacker News (Algolia API), Google News RSS, '
        'TechCrunch, GitHub search, dev.to. All are public and keyless. '
        'This page indexes headlines and links out; it does not store or '
        'republish article text. Want the tools instead? '
        '<a href="/tools/">Browse all tools</a>.</p>'
    )
    body.append("</div>")

    return "<!-- wp:html -->\n" + "\n".join(body) + "\n<!-- /wp:html -->"


def publish(content):
    # does the page already exist?
    r = requests.get(BASE + "/wp-json/wp/v2/pages",
                     params={"slug": SLUG, "_fields": "id,slug,link,title"},
                     auth=_auth(), timeout=60,
                     headers={"User-Agent": "trends-bot/1.0"})
    r.raise_for_status()
    existing = r.json()

    if existing:
        pid = existing[0]["id"]
        print(f"updating existing page id={pid} link={existing[0].get('link')}")
        rr = requests.post(BASE + f"/wp-json/wp/v2/pages/{pid}",
                           auth=_auth(), timeout=90,
                           headers={"Content-Type": "application/json",
                                    "User-Agent": "trends-bot/1.0"},
                           json={"content": content})
    else:
        print(f"creating new page slug='{SLUG}'")
        rr = requests.post(BASE + "/wp-json/wp/v2/pages",
                           auth=_auth(), timeout=90,
                           headers={"Content-Type": "application/json",
                                    "User-Agent": "trends-bot/1.0"},
                           json={"title": TITLE, "slug": SLUG,
                                 "status": "publish", "content": content})

    print(f"write -> {rr.status_code}")
    if rr.status_code not in (200, 201):
        print(rr.text[:400])
        return None
    j = rr.json()
    print(f"page id={j.get('id')} link={j.get('link')}")
    return j


if __name__ == "__main__":
    content = build()
    print(f"built content: {len(content)} chars")
    with open("trends_page.html", "w", encoding="utf-8") as f:
        f.write(content)
    print("saved -> trends_page.html")

    if "--push" in sys.argv:
        publish(content)
    else:
        print("--push not passed; nothing written to WP.")
