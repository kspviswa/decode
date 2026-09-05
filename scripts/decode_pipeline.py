#!/usr/bin/env python3
"""Decode curation — heavy lifting (collect, dedupe, tag, score, shortlist).

Supports two cadences:
  --daily (default): 48h freshness window, per-lane shortlist top 6.
  --weekly:          168h (7-day) freshness window, HN Algolia past-week search
                     in addition to the front page, per-lane shortlist top 8 so
                     the curator can pick a balanced 15-16.

Sources (user-mandated 2026-08-24): HN front page, Reddit RSS, LinkedIn + X via
uttaram MCP keyword search, and general Uttaram search on Viswa's interests.
NO aggregation sites (grep.shantanugoel.com / tdd.cat), NO direct arXiv/Substack
fetch — those surfaces may still appear organically via Uttaram search results.
Produces candidates.json (all) and shortlist.json (top N per lane).
"""
import argparse, json, os, re, sys, time, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone

SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(SOURCE_DIR, "..", "work")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

# uttaram MCP endpoint (SearxNG search + crawl). Tools are JSON-RPC over HTTP POST.
UTTARAM_URL = os.environ.get("UTTARAM_URL", "http://192.168.0.18:7777/api/mcp")
UTTARAM_KEYWORDS = [
    "site:linkedin.com telecom",
    "site:linkedin.com network intelligence",
    "site:linkedin.com network slicing OR packet core",
    "site:linkedin.com LLM OR AI agents telecom",
    "site:linkedin.com 3GPP OR 6G OR AI-RAN",
    "site:linkedin.com distributed systems OR datacenter networking",
    "site:x.com telecom OR network intelligence OR slicing OR AI-RAN",
    "site:x.com LLM OR agent OR distributed systems",
]

# General interest search (no site: restriction) — Uttaram surfaces blogs,
# GitHub, arXiv, vendor sites, etc. based on Viswa's current interests.
# NOTE: databases/storage topics deliberately excluded (user: not interesting).
UTTARAM_GENERAL_KEYWORDS = [
    "LLM agents telecom network management OR packet core OR slicing",
    "autonomous network LLM multi-agent",
    "local edge inference open-weight models",
    "structured RAG retrieval LLM",
    "distributed systems cloud-native LLM",
]

def mcp_call(name, arguments, timeout=25):
    """Call an uttaram MCP tool over HTTP (JSON-RPC). Returns parsed result."""
    body = json.dumps({"jsonrpc": "2.0", "id": int(time.time() * 1000),
                       "method": "tools/call", "params": {"name": name, "arguments": arguments}}).encode()
    req = urllib.request.Request(UTTARAM_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    if "error" in d:
        raise RuntimeError(d["error"])
    # result.content[] each has .text (a JSON string for search)
    text = "".join(c.get("text", "") for c in d["result"]["content"] if c.get("type") == "text")
    return text

def collect_mcp():
    """LinkedIn + X via uttaram MCP keyword search (SearxNG).

    The search engine often returns NO pubdate for LinkedIn/X (null), so we
    bias every query toward RECENT results (time_range=week) to avoid surfacing
    months-old posts. Items without a usable date are still collected but are
    flagged with date='' and must be verified fresh downstream; they are NOT
    auto-trusted as "today".
    """
    out = []
    for q in UTTARAM_KEYWORDS:
        try:
            txt = mcp_call("search", {"query": q, "pageno": 1, "time_range": "week"})
            j = json.loads(txt)
            for r in j.get("results", []):
                url = r.get("url") or ""
                if not url or "linkedin.com" not in url and "x.com" not in url:
                    continue
                out.append({"title": r.get("title", ""), "link": url,
                            "date": r.get("pubdate") or r.get("publishedDate") or "",
                            "source": "LinkedIn" if "linkedin.com" in url else "X",
                            "content": r.get("content", "")})
        except Exception as e:
            print("mcp err:", q, e)
    return out

def collect_mcp_general():
    """Uttaram search on Viswa's interests (any site, no site: restriction)."""
    out = []
    for q in UTTARAM_GENERAL_KEYWORDS:
        try:
            txt = mcp_call("search", {"query": q, "pageno": 1, "time_range": "week"})
            j = json.loads(txt)
            for r in j.get("results", []):
                url = r.get("url") or ""
                if not url:
                    continue
                out.append({"title": r.get("title", ""), "link": url,
                            "date": r.get("pubdate") or r.get("publishedDate") or "",
                            "source": "Uttaram", "content": r.get("content", "")})
        except Exception as e:
            print("mcp general err:", q, e)
    return out

# Lane keyword lexicons (coarse classifier)
LANES = {
    "telecom": ["telecom", "network intelligence", "network slicing", "packet core",
                "5g", "6g", "3gpp", "ai-ran", "o-ran", "ran", "nfv", "sdn", "mec",
                "autonomous network", "network automation", "core network", "mocn"],
    "ai": ["llm", "large language model", "agent", "rag", "fine-tun", "local llm",
           "open-weight", "quantiz", "model serving", "reasoning model", "inference",
           "transformer", "multimodal", "vlm", "deep learning", "gpt", "ollama"],
    "distributed-systems": ["distributed system", "kubernetes", "consensus", "raft",
                            "paxos", "storage", "datacenter", "cloud",
                            "microservice", "message queue", "streaming", "spark"],
    "longform": ["substack", "essay", "deep dive", "analysis", "opinion", "newsletter"],
}

def http_get(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

def parse_feed(text):
    """Naive RSS/Atom item extractor (title, link, pubdate)."""
    items = []
    for m in re.finditer(r"<item>(.*?)</item>|<entry>(.*?)</entry>", text, re.S):
        chunk = m.group(1) or m.group(2)
        t = re.search(r"<title[^>]*>(.*?)</title>", chunk, re.S)
        l = re.search(r"<link[^>]*>(.*?)</link>", chunk, re.S)
        d = re.search(r"<pubDate[^>]*>(.*?)</pubDate>|<published[^>]*>(.*?)</published>", chunk, re.S)
        items.append({
            "title": re.sub(r"<.*?>", "", t.group(1)).strip() if t else "",
            "link": (l.group(1).strip() if l else "").replace("&amp;", "&"),
            "date": (d.group(1) or d.group(2) or "").strip(),
        })
    return items

def collect_hn(hours=48):
    """Collect HN items from the REAL front page at https://news.ycombinator.com.

    User rule (2026-08-20): 'HN' means ONLY the live front page HTML at
    news.ycombinator.com — NOT the Algolia API (hn.algolia.com), which ranks by
    points and returns a different/stale order. Parse the actual page.
    """
    out = []
    try:
        html = http_get("https://news.ycombinator.com/")
        # titleline spans hold the story titles + links
        titles = re.findall(r'class="titleline"><a[^>]*>(.*?)</a>', html, re.S)
        links = re.findall(r'class="titleline"><a href="([^"]+)"', html)
        # score spans: <span class="score" id="score_12345">NNN points</span>
        scores = [int(x) for x in re.findall(r'<span class="score" id="score_\d+">(\d+) points</span>', html)]
        for i, title in enumerate(titles):
            raw = re.sub(r'<[^>]+>', '', title).replace('&#x27;', "'").strip()
            link = links[i] if i < len(links) else ""
            # relative /item?id= links stay on HN; external links are direct
            if link.startswith("item?"):
                link = "https://news.ycombinator.com/" + link
            pts = scores[i] if i < len(scores) else 0
            out.append({"title": raw, "link": link,
                        "date": datetime.now(timezone.utc).isoformat(),
                        "source": "HN", "points": pts})
    except Exception as e:
        print("HN front-page err:", e)
    return out

# Core interest keyword fragments used for the weekly Algolia past-week search.
ALGOLIA_KEYWORDS = [
    "telecom network AI",
    "packet core LLM",
    "network slicing agent",
    "autonomous network multi-agent",
    "local edge inference LLM",
    "structured RAG",
    "distributed systems cloud-native LLM",
    "3GPP 6G AI",
]

def collect_hn_algolia(hours=168, keywords=ALGOLIA_KEYWORDS, max_per_query=20):
    """Weekly HN collection via the Algolia Search API (search_by_date).

    The front page only covers the last day or two; for the weekly window we
    also query the Algolia search_by_date endpoint for each core interest
    keyword with numericFilters=created_at_i><cutoff> so anything from the past
    7 days surfaces. Runs IN ADDITION to the real front page (which stays the
    primary HN signal for recency).
    """
    cutoff = int(time.time()) - hours * 3600
    out = []
    for kw in keywords:
        try:
            u = ("https://hn.algolia.com/api/v1/search_by_date?"
                 f"query={urllib.parse.quote(kw)}"
                 f"&numericFilters=created_at_i%3E{cutoff}"
                 f"&hitsPerPage={max_per_query}")
            j = json.loads(http_get(u))
            for hit in j.get("hits", []):
                title = hit.get("title") or hit.get("story_title") or ""
                link = hit.get("url") or ""
                if not title:
                    continue
                if not link:
                    oid = hit.get("objectID")
                    link = f"https://news.ycombinator.com/item?id={oid}" if oid else ""
                out.append({"title": title, "link": link,
                            "date": hit.get("created_at") or "",
                            "source": "HN", "points": hit.get("points") or 0,
                            "algolia": True})
        except Exception as e:
            print("HN algolia err:", kw, e)
    return out

def collect_arxiv(cats=("cs.NI", "eess.SP", "cs.AI", "cs.LG", "cs.DC"), hours=48):
    out = []
    for cat in cats:
        try:
            u = (f"https://export.arxiv.org/api/query?search_query=cat:{cat}"
                 f"&sortBy=submittedDate&sortOrder=descending&max_results=20")
            txt = http_get(u)
            for m in re.finditer(r"<entry>(.*?)</entry>", txt, re.S):
                e = m.group(1)
                t = re.search(r"<title[^>]*>(.*?)</title>", e, re.S)
                l = re.search(r"<id[^>]*>(.*?)</id>", e, re.S)
                d = re.search(r"<published[^>]*>(.*?)</published>", e, re.S)
                out.append({"title": re.sub(r"\s+", " ", re.sub(r"<.*?>", "", t.group(1))).strip() if t else "",
                            "link": l.group(1).strip() if l else "",
                            "date": d.group(1).strip() if d else "",
                            "source": "arXiv", "cat": cat})
        except Exception as e:
            print(f"arxiv {cat} err:", e)
    return out

def collect_reddit(subs=("LocalLLaMA", "MachineLearning"), hours=48):
    out = []
    top = "week" if hours >= 7 * 24 else "day"
    for s in subs:
        try:
            u = f"https://www.reddit.com/r/{s}/top/.rss?t={top}"
            for it in parse_feed(http_get(u)):
                it["source"] = "Reddit"
                out.append(it)
        except Exception as e:
            print(f"reddit {s} err:", e)
    return out

def collect_substack(feeds=()):
    out = []
    for f in feeds:
        try:
            for it in parse_feed(http_get(f)):
                it["source"] = "Substack"
                out.append(it)
        except Exception as e:
            print(f"substack {f} err:", e)
    return out

def tag(item):
    text = f"{item.get('title','')} {item.get('content','')}".lower()
    scores = {}
    for lane, kws in LANES.items():
        scores[lane] = sum(1 for k in kws if k in text)
    best = max(scores, key=scores.get)
    item["lane"] = best if scores[best] > 0 else "wildcard"
    item["lane_scores"] = scores
    return item

def score(item):
    """Score an item.

    User rule (2026-08-20): use points ONLY for point-bearing sources (HN,
    Reddit). For all other sources (LinkedIn, X, Uttaram, GitHub, Blog), points
    don't apply — rank by keyword/lane relevance first, and let the final LLM
    curation step pick. This stops proxy sources (LinkedIn/X) and raw sources
    (arXiv/GitHub via Uttaram) from being swallowed by point-based ranking.
    """
    s = 0
    if item.get("source") in ("HN", "Reddit"):
        s += item.get("points", 0)
    # keyword/lane relevance is the primary signal for non-point sources
    s += item["lane_scores"].get(item["lane"], 0) * 3
    item["score"] = s
    return item

def dedupe(items, seen_links):
    out = []
    for it in items:
        if not it.get("link"):
            continue
        key = it["link"].split("?")[0].rstrip("/")
        if key in seen_links:
            continue
        seen_links.add(key)
        out.append(it)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=48)
    ap.add_argument("--weekly", action="store_true",
                    help="weekly mode: 168h window, HN Algolia past-week search, per-lane top 8")
    ap.add_argument("--extra", action="append", default=[], help="JSON file of pre-collected LinkedIn/X results")
    ap.add_argument("--reed", action="store_true", help="load previously-seen links from work/seen.json")
    args = ap.parse_args()

    hours = 168 if args.weekly else args.hours
    top = 8 if args.weekly else 6

    os.makedirs(OUT, exist_ok=True)
    seen = set()
    if args.reed and os.path.exists(os.path.join(OUT, "seen.json")):
        seen = set(json.load(open(os.path.join(OUT, "seen.json"))))

    items = []
    items += collect_hn(hours)
    if args.weekly:
        items += collect_hn_algolia(hours)
    items += collect_reddit(hours=hours)
    items += collect_mcp()  # LinkedIn + X via uttaram MCP
    items += collect_mcp_general()  # Uttaram search on interests (any site)
    for f in args.extra:
        try:
            with open(f) as _f:
                items += json.load(_f)
        except Exception as e:
            print("extra err:", f, e)

    items = dedupe(items, seen)
    items = [tag(i) for i in items]
    items = [score(i) for i in items]

    # freshness drop (keep within window unless source says otherwise)
    cutoff = time.time() - hours * 3600
    fresh = []
    for i in items:
        datestr = (i.get("date") or "").strip()
        dt = None
        if datestr:
            try:
                dt = datetime.fromisoformat(datestr.replace("Z", "+00:00")).timestamp()
            except Exception:
                dt = None
        if i["source"] in ("Reddit", "HN"):
            # Reddit top-of-day is inherently recent; HN front page is live,
            # and Algolia items were fetched with a created_at_i cutoff.
            fresh.append(i)
        elif dt is not None and dt >= cutoff:
            fresh.append(i)
        # Undated LinkedIn/X/Uttaram items are NOT trusted as fresh — they must
        # be verified during curation; drop them from the auto-shortlist to avoid
        # surfacing months-old posts as "today".
    items = fresh

    all_path = os.path.join(OUT, "candidates.json")
    with open(all_path, "w") as _f:
        json.dump(items, _f, indent=2)

    # per-lane shortlist (top 6 daily / top 8 weekly), sorted by score
    short = {}
    # Reserved-source guarantee: these proxy sources must each appear at least
    # once across the shortlist (user-mandated primary-source policy) so they
    # are never swallowed by point/lane ranking. HN is the top priority.
    reserved = {"HN": 2, "LinkedIn": 1, "X": 1}
    placed = set()
    for lane in ["telecom", "ai", "distributed-systems", "longform", "wildcard"]:
        pool = sorted([i for i in items if i["lane"] == lane], key=lambda x: x["score"], reverse=True)
        lane_items = []
        # First pass: force-reserve required sources into this lane if available
        for src, need in reserved.items():
            if src in placed or need == 0:
                continue
            for it in pool:
                if it["source"] == src and it not in lane_items:
                    lane_items.append(it)
                    if src in ("HN", "LinkedIn", "X"):
                        placed.add(src)
                    break
        # Second pass: fill remaining slots by score
        for it in pool:
            if it not in lane_items:
                lane_items.append(it)
            if len(lane_items) >= top:
                break
        short[lane] = lane_items[:top]
    short_path = os.path.join(OUT, "shortlist.json")
    with open(short_path, "w") as _f:
        json.dump(short, _f, indent=2)

    with open(os.path.join(OUT, "seen.json"), "w") as _f:
        json.dump(sorted(seen), _f, indent=2)

    print(f"mode={'weekly' if args.weekly else 'daily'} hours={hours} top={top}/lane  collected={len(items)}  seen={len(seen)}")
    for lane in short:
        print(f"  [{lane}] {len(short[lane])}: " + "; ".join(i['title'][:40] for i in short[lane]))
    print("wrote", all_path, short_path)

if __name__ == "__main__":
    main()
