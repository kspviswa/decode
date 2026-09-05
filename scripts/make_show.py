#!/usr/bin/env python3
"""Decode biweekly two-host show builder.

Runs ~every other Saturday (cron job b2c4d6e8) and converts the 2-3 weekly
digest editions since the last episode into a single ~30-minute two-host show
(Avery + Jordan) that is pushed into Shravana under the `podcast` category.

Two modes:

  1. ASSEMBLE (default):      idempotent aggregation + grouping + validation.
     - Reads work/last_show.json  ({"date": "YYYY-MM-DD"}, default: epoch).
     - Collects posts/<YYYY-MM-DD>/stories.yml for every digest after the last
       show, sorted ascending (usually 2-3 weekly editions).
     - Groups stories by lane/section (same mapping as the digest template).
     - Writes work/show_script.json as a validated scaffold for the pipeline
       LLM (Sarathy) to fill in: {"title", "lines": [], "_meta": {...}} with a
       word-count target header of ~4,300-5,200 words (~30 min @ ~145 wpm).
       Existing non-empty scripts are NOT overwritten (idempotent).

  2. SYNTH (--synth --out <mp3>):  synthesize + push + marker.
     - Validates work/show_script.json (schema + word-count target).
     - Synthesizes with the local kokoro backend (shravana venv, avery ->
       af_heart, jordan -> am_michael), chunked so long ~30-min scripts are
       never truncated, and concatenated with ffmpeg.
     - Pushes the MP3 to Shravana:
         POST /api/books/upload?filename=Decode%20Show%20-%20X%20to%20Y.mp3&category=podcast
     - Verifies HTTP 201 + book state 'complete' (polls twice, short sleep).
     - Writes work/last_show.json ONLY after a successful push.

No GitHub push for the show — the show lives only in Shravana.
"""
import argparse, json, os, re, subprocess, sys, tempfile, time, urllib.parse, urllib.request
from datetime import date

SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SOURCE_DIR)
POSTS_DIR = os.path.join(REPO_DIR, "posts")
WORK_DIR = os.path.join(REPO_DIR, "work")
MARKER = os.path.join(WORK_DIR, "last_show.json")
SCRIPT_PATH = os.path.join(WORK_DIR, "show_script.json")
DEFAULT_SCRIPT = SCRIPT_PATH

SHRAVANA_UPLOAD = "http://127.0.0.1:27388/api/books/upload"
SHRAVANA_BOOKS = "http://127.0.0.1:27388/api/books/{bid}"

# ~30 minute two-host show (~145 wpm) word-count target (script header meta).
WORD_TARGET_MIN = 4300
WORD_TARGET_MAX = 5200
DEFAULT_GAP = 0.5

# Slide: lane/category -> digest section. First section whose categories
# intersect wins; stories with no matching category fall back to Research.
SECTION_ORDER = [
    "Networks · 5G & 6G",
    "Security",
    "AI & Models",
    "Business & Funding",
    "Research & World Models",
]
SECTION_BY_CATEGORY = {
    # Networks · 5G & 6G
    "5g": "Networks · 5G & 6G", "6g": "Networks · 5G & 6G",
    "5g-core": "Networks · 5G & 6G", "spectrum": "Networks · 5G & 6G",
    "slicing": "Networks · 5G & 6G", "tsn": "Networks · 5G & 6G",
    "ai-ran": "Networks · 5G & 6G", "network-intelligence": "Networks · 5G & 6G",
    "industrial": "Networks · 5G & 6G",
    # Security
    "ai-security": "Security", "security": "Security",
    # AI & Models
    "ai-infra": "AI & Models", "llm": "AI & Models",
    "open-weights": "AI & Models", "local-llm": "AI & Models",
    "benchmarks": "AI & Models", "vision": "AI & Models",
    "vlm": "AI & Models", "openai": "AI & Models",
    "ai-agents": "AI & Models", "llm-agents": "AI & Models",
    "edge-inference": "AI & Models", "ci-cd": "AI & Models",
    # Business & Funding
    "m-and-a": "Business & Funding",
    # Research & World Models
    "digital-twin": "Research & World Models", "world-models": "Research & World Models",
    "generative": "Research & World Models", "simulation": "Research & World Models",
    "agents": "Research & World Models",
}


def read_marker(marker=MARKER):
    """Return last-show date as 'YYYY-MM-DD'; epoch (1970-01-01) if missing."""
    if os.path.exists(marker):
        try:
            with open(marker) as f:
                return json.load(f).get("date", "1970-01-01")
        except Exception:
            return "1970-01-01"
    return "1970-01-01"


def digest_dirs_since(last_date, posts_dir=POSTS_DIR):
    """Return sorted posts/<YYYY-MM-DD>/ dirs strictly after last_date."""
    out = []
    for name in sorted(os.listdir(posts_dir)):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", name):
            continue
        if name > last_date:
            out.append(os.path.join(posts_dir, name))
    return out


def load_stories(day_dir):
    """Load the stories list from a digest day's stories.yml ([] if absent)."""
    path = os.path.join(day_dir, "stories.yml")
    if not os.path.exists(path):
        return []
    try:
        import yaml
    except ImportError:
        sys.stderr.write("PyYAML required for stories.yml parsing\n")
        raise
    with open(path) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, list):
        return []
    out = []
    day = os.path.basename(day_dir)
    for s in data:
        if not isinstance(s, dict) or not s.get("title"):
            continue
        s = dict(s)
        s["day"] = day
        out.append(s)
    return out


def aggregate_stories(day_dirs):
    """Aggregate {day, title, categories, tldr, why, source, link} per story."""
    out = []
    for d in day_dirs:
        for s in load_stories(d):
            out.append({
                "day": s.get("day") or os.path.basename(d),
                "title": s.get("title", ""),
                "categories": s.get("categories") or [],
                "tldr": s.get("tldr") or [],
                "why": s.get("why", ""),
                "source": s.get("source", ""),
                "link": s.get("link", ""),
            })
    return out


def section_for(categories):
    """Map a story's categories to a digest section (first hit wins)."""
    cats = [str(c).lower() for c in (categories or [])]
    for c in cats:
        sec = SECTION_BY_CATEGORY.get(c)
        if sec:
            return sec
    return "Research & World Models"


def group_by_section(stories):
    """Return {section: [story, ...]} in SECTION_ORDER incl. empty sections."""
    groups = {s: [] for s in SECTION_ORDER}
    for st in stories:
        groups[section_for(st.get("categories"))].append(st)
    return groups


def count_words(script):
    """Word count across all script lines."""
    total = 0
    for line in script.get("lines", []):
        total += len(str(line.get("text", "")).split())
    return total


def validate_script(script):
    """Validate show_script.json schema + word-count target.

    Returns (ok, errors, word_count).  Word-count is advisory (warn only) but
    a schema problem (missing title / malformed lines) is an error.
    """
    errors = []
    if not isinstance(script, dict):
        return False, ["script is not a JSON object"], 0
    if "title" not in script:
        errors.append("missing 'title'")
    lines = script.get("lines", [])
    if not isinstance(lines, list):
        errors.append("'lines' is not a list")
        return False, errors, 0
    for i, line in enumerate(lines):
        if not isinstance(line, dict):
            errors.append(f"line {i}: not an object")
            continue
        speaker = line.get("speaker", "avery")
        if speaker not in ("avery", "jordan"):
            errors.append(f"line {i}: speaker must be avery|jordan, got {speaker!r}")
        if not isinstance(line.get("text", ""), str) or not line.get("text", "").strip():
            errors.append(f"line {i}: missing/empty 'text'")
    n = count_words(script)
    if errors:
        return False, errors, n
    if n < WORD_TARGET_MIN or n > WORD_TARGET_MAX:
        errors.append(f"word count {n} outside target [{WORD_TARGET_MIN}, {WORD_TARGET_MAX}]")
        return False, errors, n
    return True, errors, n


def build_scaffold(days, stories, groups, first_day, last_day):
    """Assemble the show_script scaffold the pipeline LLM fills in."""
    # The word-count target lives in the script "header" metadata so Sarathy
    # knows the budget while writing the dialogue (schema stays compatible with
    # make_podcast_kokoro.py which only reads title + lines).
    meta = {
        "kind": "show",
        "covered_days": days,
        "first_day": first_day,
        "last_day": last_day,
        "story_count": len(stories),
        "word_target_min": WORD_TARGET_MIN,
        "word_target_max": WORD_TARGET_MAX,
        "sections": {sec: len(st) for sec, st in groups.items() if st},
        "stories": [
            {"title": s["title"], "link": s["link"], "source": s["source"],
             "day": s["day"], "section": section_for(s.get("categories"))}
            for s in stories
        ],
        "notes": "Fill 'lines' with a natural Avery+Jordan dialogue: intro "
                 "(welcome, hosts, editor Sarathy, listener Viswa, what this "
                 "week's editions cover), one segment per lane covering that "
                 "lane's stories with transitions, outro (wrap-up + public-"
                 "benefit note). Target %s-%s words (~30 min)." % (WORD_TARGET_MIN, WORD_TARGET_MAX),
    }
    return {"title": f"Decode Show — {first_day} to {last_day}", "lines": [], "_meta": meta}


def assemble(posts_dir=POSTS_DIR, marker=MARKER, script_path=SCRIPT_PATH, today=None):
    """Aggregate digests since the last show, group by lane, write scaffold.

    Returns a dict report; exits empty-hearted (no work) when there's nothing
    new. Never clobbers an existing non-empty script.
    """
    today = today or date.today().isoformat()
    last = read_marker(marker)
    os.makedirs(os.path.dirname(script_path), exist_ok=True)
    if last == today:
        return {"status": "already-built", "last_show": last, "today": today,
                "message": "a show was already built today; nothing to do"}

    day_dirs = digest_dirs_since(last, posts_dir)
    stories = aggregate_stories(day_dirs)
    if not stories:
        return {"status": "nothing-new", "last_show": last, "today": today,
                "message": "no digest editions since the last show"}

    days = sorted({s["day"] for s in stories})
    first_day, last_day = days[0], days[-1]
    groups = group_by_section(stories)

    # Only write the scaffold if a script isn't already drafted (idempotent).
    wrote = False
    if not os.path.exists(script_path):
        with open(script_path, "w") as f:
            json.dump(build_scaffold(days, stories, groups, first_day, last_day), f, indent=2)
        wrote = True
    else:
        try:
            with open(script_path) as f:
                existing = json.load(f)
            if not existing.get("lines"):
                with open(script_path, "w") as f:
                    json.dump(build_scaffold(days, stories, groups, first_day, last_day), f, indent=2)
                wrote = True
        except Exception:
            pass

    return {"status": "assembled", "wrote": wrote, "last_show": last, "today": today,
            "first_day": first_day, "last_day": last_day,
            "covered_days": days, "story_count": len(stories),
            "sections": {k: len(v) for k, v in groups.items() if v}}


# ---------------------------------------------------------------------------
# Kokoro synthesis (lazy import — only needed in the shravana venv)
# ---------------------------------------------------------------------------

def import_kokoro():
    """Import the kokoro synthesis helpers from make_podcast_kokoro.py.

    Purely lazy: this imports tts_kokoro from the shravana venv, so it must
    only run inside that venv (make_show optionally used in tests without it).
    """
    sys.path.insert(0, SOURCE_DIR)
    import make_podcast_kokoro as mpk  # noqa: E402
    return mpk


def synth_chunked(backend, mpk, lines, speed, tmp):
    """Synthesize lines into a list of wav paths in `tmp`.

    Chunked: each turn is its own WAV (with optional trailing silence), so a
    30-minute script is synthesized turn-by-turn and concatenated once with
    ffmpeg — no truncation, no unbounded memory.
    """
    parts = []
    for i, line in enumerate(lines):
        speaker = line.get("speaker", "avery").lower()
        voice = mpk.VOICES.get(speaker, mpk.VOICES["avery"])
        wav = os.path.join(tmp, f"seg_{i:04d}.wav")
        pcm = backend.synthesize(line["text"], voice=voice, speed=speed)
        mpk.write_wav(wav, pcm)
        parts.append(wav)
        gap = line.get("gap_after", DEFAULT_GAP)
        if gap > 0 and i < len(lines) - 1:
            sil = os.path.join(tmp, f"sil_{i:04d}.wav")
            mpk.make_silence(gap, sil)
            parts.append(sil)
    return parts


def concat_to_mp3(parts, out_mp3, tmp):
    """Concatenate WAV parts into a single MP3 via ffmpeg."""
    # Split into chunks of ~60 files, encode each chunk to mp3, then concat.
    chunk_mp3s = []
    step = 60
    for c in range(0, len(parts), step):
        chunk_parts = parts[c:c + step]
        clist = os.path.join(tmp, f"chunk_{c}.txt")
        with open(clist, "w") as f:
            for p in chunk_parts:
                f.write(f"file '{p}'\n")
        chunk_mp3 = os.path.join(tmp, f"chunk_{c}.mp3")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", clist,
                        "-c:a", "libmp3lame", "-b:a", "96k", chunk_mp3],
                       check=True, capture_output=True)
        chunk_mp3s.append(chunk_mp3)

    if len(chunk_mp3s) == 1:
        import shutil
        shutil.copy(chunk_mp3s[0], out_mp3)
        return

    clist = os.path.join(tmp, "chunks.txt")
    with open(clist, "w") as f:
        for p in chunk_mp3s:
            f.write(f"file '{p}'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", clist,
                    "-c:a", "libmp3lame", "-b:a", "96k", out_mp3],
                   check=True, capture_output=True)


def mp3_duration(out_mp3):
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", out_mp3],
            capture_output=True, text=True)
        return float(probe.stdout.strip())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Shravana push (job 66 capability — do NOT modify shravana)
# ---------------------------------------------------------------------------

def show_filename(first_day, last_day):
    """Decode Show - <start> to <end>.mp3  (hyphen form, URL-safe)."""
    return f"Decode Show - {first_day} to {last_day}.mp3"


def push_mp3(mp3_path, first_day, last_day, upload_url=SHRAVANA_UPLOAD):
    """POST the MP3 to Shravana; return (http_status, body).

    Content-Type: octet-stream; filename + category are query params.
    """
    params = urllib.parse.urlencode({"filename": show_filename(first_day, last_day),
                                     "category": "podcast"})
    with open(mp3_path, "rb") as f:
        data = f.read()
    req = urllib.request.Request(f"{upload_url}?{params}", data=data, method="POST")
    req.add_header("Content-Type", "application/octet-stream")
    with urllib.request.urlopen(req, timeout=600) as r:
        body = json.loads(r.read().decode("utf-8", "replace"))
        return r.status, body


def fetch_book(bid, books_url=SHRAVANA_BOOKS):
    """GET /api/books/<id>; return parsed body ({} on any failure)."""
    try:
        with urllib.request.urlopen(books_url.format(bid=bid), timeout=30) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        print("poll book err:", e)
        return {}


def verify_complete(bid, sleep=1.0):
    """Poll the book twice (short sleep) and confirm state == 'complete'."""
    for _ in range(2):
        time.sleep(sleep)
        b = fetch_book(bid)
        if isinstance(b, dict) and b.get("state") == "complete":
            return True, b
    return False, b


def write_marker(marker=MARKER, when=None):
    when = when or date.today().isoformat()
    os.makedirs(os.path.dirname(marker), exist_ok=True)
    json.dump({"date": when}, open(marker, "w"), indent=2)


def push_and_mark(out_mp3, first_day, last_day, marker=MARKER):
    """Push the MP3 to Shravana, verify, then write last_show.json.

    The marker is written ONLY after a successful push (or a Shravana
    duplicate, which means the show was already imported). Raises RuntimeError
    on any failure so the marker is never updated for a show that did not land.
    """
    status, body = push_mp3(out_mp3, first_day, last_day)
    if not isinstance(body, dict):
        raise RuntimeError(f"push failed: unexpected response body {body!r}")
    bid = body.get("id")
    if body.get("duplicate"):
        print(f"Shravana reports duplicate import (id={bid}) — show already "
              "pushed; updating marker.")
    elif status == 201 and bid:
        complete, book = verify_complete(bid)
        if not complete:
            raise RuntimeError(f"push returned 201 (id={bid}) but book did not "
                               f"reach 'complete' state: {book!r}")
        print(f"Shravana book {bid} complete.")
    else:
        raise RuntimeError(f"push failed: HTTP {status} body={body!r}")
    write_marker(marker)
    return {"status": "pushed", "shravana_book_id": bid, "category": "podcast",
            "out": out_mp3}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Decode biweekly two-host show builder")
    ap.add_argument("--synth", action="store_true",
                    help="synthesize + push instead of assemble/validate")
    ap.add_argument("--script", default=DEFAULT_SCRIPT,
                    help="show script path (default work/show_script.json)")
    ap.add_argument("--out", default=None, help="output mp3 path (default work/show_<date>.mp3)")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--no-push", action="store_true",
                    help="synthesize but do NOT push to Shravana or touch the marker")
    ap.add_argument("--marker", default=MARKER)
    args = ap.parse_args()

    if args.synth:
        synth(args)
    else:
        rep = assemble(marker=args.marker, script_path=args.script)
        print(json.dumps(rep, indent=2))


def synth(args):
    if not os.path.exists(args.script):
        sys.exit(f"no show script at {args.script} — run assembly first, then have "
                 "Sarathy write the lines into it")
    with open(args.script) as f:
        script = json.load(f)
    ok, errors, n = validate_script(script)
    if not ok:
        sys.exit("show_script.json invalid:\n- " + "\n- ".join(errors))

    meta = script.get("_meta", {})
    first_day = meta.get("first_day") or (script.get("title", "").split(" — ")[-1].split(" to ")[0])
    last_day = meta.get("last_day")
    if not last_day:
        m = re.search(r"to (\d{4}-\d{2}-\d{2})", script.get("title", ""))
        last_day = m.group(1) if m else date.today().isoformat()

    today = date.today().isoformat()
    if read_marker(args.marker) == today:
        print("last_show.json already marks today; show already produced — exiting.")
        return

    out_mp3 = args.out
    if not out_mp3:
        out_mp3 = os.path.join(WORK_DIR, f"show_{today}.mp3")
    os.makedirs(os.path.dirname(out_mp3), exist_ok=True)

    print(f"Loading kokoro model (local TTS)...", flush=True)
    mpk = import_kokoro()
    backend = mpk.KokoroOnnxBackend(
        os.path.join(mpk.MODELS_DIR, "kokoro-v1.0.onnx"),
        os.path.join(mpk.MODELS_DIR, "voices-v1.0.bin"),
    )
    lines = script["lines"]
    print(f"Synth {len(lines)} turns, {n} words ({n / 145.0:.1f} min expected)...", flush=True)

    with tempfile.TemporaryDirectory() as tmp:
        parts = synth_chunked(backend, mpk, lines, args.speed, tmp)
        print(f"Concatenating {len(parts)} parts -> {out_mp3} ...", flush=True)
        concat_to_mp3(parts, out_mp3, tmp)

    duration = mp3_duration(out_mp3)
    dur_text = f"{duration / 60.0:.1f} min" if duration else "unknown"

    if args.no_push:
        print(f"DRY-RUN: synthesized {out_mp3} ({dur_text}); NOT pushed to Shravana; "
              "marker untouched.")
        return

    print(f"Pushing {out_mp3} to Shravana ({dur_text})...", flush=True)
    rep = push_and_mark(out_mp3, first_day, last_day, args.marker)
    rep["duration_min"] = round(duration / 60.0, 1) if duration else None
    rep["word_count"] = n
    rep["covered_days"] = meta.get("covered_days")
    rep["story_count"] = meta.get("story_count")
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()