#!/usr/bin/env python3
"""Generate / update the Decode Daily podcast RSS feed (podcast.xml).

Appends today's episode using the day's mp3, with metadata aligned to the
existing 'Techno Adventure Podcast' (owner email, categories, explicit, author).

Feed: RSS 2.0 + Apple Podcasts (itunes) + Atom namespaces.
Required for Spotify / Apple Podcasts submission.

Usage:
  .venv-tts/bin/python scripts/make_podcast_feed.py --date YYYY-MM-DD
"""
import argparse, os, re, subprocess, sys
from datetime import datetime, timezone

SITE = "https://decode.viswakumar.com"
FEED_PATH = "podcast.xml"
COVER = f"{SITE}/podcast_cover.png"

# Metadata aligned with the existing 'Techno Adventure Podcast' feed.
OWNER_NAME = ("Brace yourself for an exhilarating journey through the twists "
              "and turns of AI/ML, telecommunications and distributed systems.")
OWNER_EMAIL = "viswakumar@substack.com"
CATEGORIES = ["Technology", "Science"]
AUTHOR = "Sarathy"
DESCRIPTION = ("Decode Daily is a hand-curated tech digest. Each day Sarathy "
               "picks the stories that matter and explains them in plain "
               "language. For Viswa Kumar, shared for public benefit.")
LANGUAGE = "en"
EXPLICIT = "No"


def get_duration(mp3):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", mp3],
        capture_output=True, text=True)
    return float(r.stdout.strip())


def fmt_duration(sec):
    sec = int(round(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def esc(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


def date_to_rfc2822(date):
    dt = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")


def make_channel_head():
    cats = "\n".join(
        f"    <itunes:category text=\"{esc(c)}\"/>" for c in CATEGORIES)
    owner = (f"    <itunes:owner>\n"
             f"      <itunes:name>{esc(OWNER_NAME)}</itunes:name>\n"
             f"      <itunes:email>{esc(OWNER_EMAIL)}</itunes:email>\n"
             f"    </itunes:owner>")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:atom="http://www.w3.org/2005/Atom" version="2.0">
<channel>
  <title>Decode Daily</title>
  <link>{SITE}/</link>
  <atom:link href="{SITE}/podcast.xml" rel="self" type="application/rss+xml"/>
  <language>{LANGUAGE}</language>
  <description>{esc(DESCRIPTION)}</description>
  <itunes:author>{esc(AUTHOR)}</itunes:author>
  <itunes:summary>{esc(DESCRIPTION)}</itunes:summary>
  <itunes:explicit>{EXPLICIT}</itunes:explicit>
{cats}
{owner}
  <itunes:image href="{COVER}"/>
  <itunes:type>episodic</itunes:type>
"""


def make_item(date, title, mp3_url, length, duration, tldr=""):
    guid = f"decode-{date}"
    pub = date_to_rfc2822(date)
    return f"""  <item>
    <title>{esc(title)}</title>
    <guid isPermaLink="false">{guid}</guid>
    <pubDate>{pub}</pubDate>
    <author>{esc(AUTHOR)}</author>
    <description>{esc(tldr)}</description>
    <itunes:title>{esc(title)}</itunes:title>
    <itunes:duration>{fmt_duration(duration)}</itunes:duration>
    <itunes:explicit>{EXPLICIT}</itunes:explicit>
    <enclosure url="{esc(mp3_url)}" length="{length}" type="audio/mpeg"/>
  </item>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--mp3", help="path to mp3 (defaults to posts/<date>/podcast.mp3)")
    ap.add_argument("--title", help="episode title (defaults to 'Decode Daily — <date>')")
    ap.add_argument("--title-desc", default="", help="short episode description")
    ap.add_argument("--out", default=FEED_PATH)
    args = ap.parse_args()

    date = args.date
    mp3 = args.mp3 or f"posts/{date}/podcast.mp3"
    if not os.path.exists(mp3):
        sys.exit(f"mp3 not found: {mp3}")

    length = os.path.getsize(mp3)
    duration = get_duration(mp3)
    title = args.title or f"Decode Daily — {date}"
    mp3_url = f"{SITE}/posts/{date}/podcast.mp3"
    tld = args.title_desc

    if os.path.exists(args.out) and os.path.getsize(args.out) > 0:
        existing = open(args.out).read()
        existing = re.sub(r"\s*</channel>\s*</rss>\s*$", "", existing)
        head = existing if "<channel>" in existing else make_channel_head()
    else:
        head = make_channel_head()

    item = make_item(date, title, mp3_url, length, duration, tld)
    feed = head + item + "</channel>\n</rss>\n"

    with open(args.out, "w") as f:
        f.write(feed)
    print(f"Feed written: {args.out}")
    print(f"  episode: {title} ({fmt_duration(duration)}, {length} bytes)")
    print(f"  enclosure: {mp3_url}")


if __name__ == "__main__":
    main()