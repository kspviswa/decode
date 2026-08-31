#!/usr/bin/env python3
"""Push today's decode curation into Manana (the reflection portal).

Reads posts/<date>/stories.yml, selects Manana-worthy stories, writes wiki
entity pages (if missing) into WIKI_ROOT/Wiki/Research/, then upserts the
day into Manana via POST /api/days.

Selection:
  - Stories with a `manana:` block (dict) are always picked.
      manana:
        slug: my-short-slug        # optional; default = auto from title
        teaser: "..."              # optional; default = first tldr bullet
        reason: "..."              # optional; default = `why`
  - If none are flagged, the first --limit stories are picked automatically.

Idempotent: POST /api/days replaces the day's items, so re-runs are safe.
Wiki entity files are only written if they don't already exist.

Usage:
  python3 scripts/push_manana.py [--date YYYY-MM-DD] [--limit N] [--dry-run]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime

import yaml

MANANA_API = os.environ.get("MANANA_API", "http://127.0.0.1:21063/api")
DECODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIKI_ROOT = os.environ.get("WIKI_ROOT", os.path.expanduser("~/wiki_root"))
WIKI_KIND = "Research"
WIKI_DIR = os.path.join(WIKI_ROOT, "Wiki", WIKI_KIND)


def today_utc() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def slugify(title: str, maxlen: int = 52) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:maxlen].rstrip("-")


def story_entity(story: dict, idx: int) -> dict:
    """Return {slug, title, teaser, reason, url, source} for a story."""
    m = story.get("manana") or {}
    if isinstance(m, dict) and m.get("slug"):
        slug = str(m["slug"])
    else:
        slug = slugify(story.get("title") or f"story-{idx}")
    tldr = story.get("tldr") or []
    teaser = (m.get("teaser") if isinstance(m, dict) else None) or (
        tldr[0] if tldr else (story.get("why") or "")
    )
    reason = (m.get("reason") if isinstance(m, dict) else None) or (story.get("why") or "")
    return {
        "slug": slug,
        "title": story.get("title") or slug,
        "teaser": teaser,
        "reason": reason,
        "url": story.get("link") or "",
        "source": "decode",
        "tags": story.get("tags") or story.get("categories") or [],
    }


def entity_md(story: dict, idx: int) -> str:
    e = story_entity(story, idx)
    tldr = story.get("tldr") or []
    bullets = "\n".join(f"- {b}" for b in tldr)
    tags = "\n".join(f"  - {t}" for t in (e["tags"][:8] or ["decode"]))
    why = story.get("why") or e["reason"]
    return f"""---
title: {e['title']}
date: {today_utc()}
tags:
{tags}
status: published
---

# {e['title']}

{why}

## TLDR

{bullets}

## Link

- [{e['title']}]({e['url']})
"""


def write_wiki_entity(slug: str, content: str, dry_run: bool) -> bool:
    """Write the wiki md if missing. Returns True if written."""
    path = os.path.join(WIKI_DIR, slug + ".md")
    if os.path.exists(path):
        return False
    if dry_run:
        print(f"  [dry-run] would write {path}")
        return True
    tmp = f"/tmp/manana_wiki_{slug}.md"
    with open(tmp, "w") as f:
        f.write(content)
    subprocess.run(["sudo", "-n", "cp", tmp, path], check=True)
    subprocess.run(["sudo", "-n", "chown", "501:dialout", path], check=True)
    os.remove(tmp)
    return True


def push_day(date: str, items: list[dict], dry_run: bool) -> dict:
    payload = {
        "date": date,
        "title": f"Manana Daily — {datetime.strptime(date, '%Y-%m-%d').strftime('%a %b %d')}",
        "items": items,
    }
    if dry_run:
        print(f"[dry-run] POST /api/days {date} with {len(items)} items")
        for it in items:
            print(f"  - {it['entity_slug']}: {it['title']}")
        return {"slug": date, "itemCount": len(items)}
    req = urllib.request.Request(
        MANANA_API + "/days",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    date = args.date or today_utc()
    stories_path = os.path.join(DECODE_DIR, "posts", date, "stories.yml")
    if not os.path.exists(stories_path):
        print(f"no stories.yml for {date}: {stories_path}", file=sys.stderr)
        return 1

    stories = yaml.safe_load(open(stories_path)) or []
    flagged = [s for s in stories if isinstance(s.get("manana"), dict)]
    picked = flagged or stories[: args.limit]
    if not picked:
        print(f"no stories picked for {date}", file=sys.stderr)
        return 1

    print(f"picked {len(picked)} stories for {date} ({'flag' if flagged else 'fallback'})")
    items = []
    for idx, story in enumerate(picked):
        e = story_entity(story, idx)
        written = write_wiki_entity(e["slug"], entity_md(story, idx), args.dry_run)
        print(f"  [{'+' if written else '='}] wiki {e['slug']}")
        items.append(
            {
                "entity_slug": e["slug"],
                "title": e["title"],
                "teaser": e["teaser"],
                "reason": e["reason"],
                "source": e["source"],
                "url": e["url"],
            }
        )

    out = push_day(date, items, args.dry_run)
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())