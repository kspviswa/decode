#!/usr/bin/env python3
"""Decode daily podcast generator.

Reads a dialogue script (work/podcast_script.json) and synthesizes a two-host
podcast with edge-tts (free Microsoft Edge neural voices), concatenating turns
with small silences via ffmpeg.

Script JSON schema:
{
  "title": "Optional title",
  "lines": [
    {"speaker": "aria"|"guy", "text": "...", "gap_after": 0.5}
  ]
}

Voices:
  aria -> en-IN-NeerjaNeural  (female, English-India)
  guy  -> en-IN-PrabhatNeural (male, English-India)

Usage:
  .venv-tts/bin/python scripts/make_podcast.py [--script work/podcast_script.json] [--out podcast.mp3]
"""
import argparse, asyncio, json, os, subprocess, sys, tempfile, time

VOICES = {
    "aria": "en-IN-NeerjaNeural",
    "guy": "en-IN-PrabhatNeural",
}
DEFAULT_GAP = 0.5  # seconds between turns


def synth_line(voice: str, text: str, out_path: str):
    import edge_tts
    async def _run():
        com = edge_tts.Communicate(text, voice, rate="+8%", pitch="+0Hz")
        await com.save(out_path)
    asyncio.run(_run())


def make_silence(duration: float, out_path: str, rate: int = 24000):
    """Generate a silence mp3 with ffmpeg."""
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i",
           f"anullsrc=r={rate}:cl=mono", "-t", f"{duration:.2f}",
           "-q:a", "9", out_path]
    subprocess.run(cmd, check=True, capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", default="work/podcast_script.json")
    ap.add_argument("--out", default="podcast.mp3")
    args = ap.parse_args()

    with open(args.script) as f:
        script = json.load(f)

    lines = script["lines"]
    print(f"Generating podcast for {len(lines)} turns...")

    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        concat_list = os.path.join(tmp, "concat.txt")

        # Synthesize each turn, interleave with silences.
        for i, line in enumerate(lines):
            speaker = line.get("speaker", "aria").lower()
            voice = VOICES.get(speaker, VOICES["aria"])
            seg = os.path.join(tmp, f"seg_{i:03d}.mp3")
            synth_line(voice, line["text"], seg)
            parts.append(seg)

            gap = line.get("gap_after", DEFAULT_GAP)
            if gap > 0 and i < len(lines) - 1:
                sil = os.path.join(tmp, f"sil_{i:03d}.mp3")
                make_silence(gap, sil)
                parts.append(sil)

        with open(concat_list, "w") as f:
            for p in parts:
                f.write(f"file '{p}'\n")

        # Concatenate all parts into the final mp3.
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
               "-c:a", "libmp3lame", "-b:a", "96k", args.out]
        subprocess.run(cmd, check=True, capture_output=True)

        # Report duration.
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", args.out],
            capture_output=True, text=True)
        try:
            dur = float(probe.stdout.strip())
            print(f"Done -> {args.out}  ({dur/60:.1f} min)")
        except ValueError:
            print(f"Done -> {args.out}")


if __name__ == "__main__":
    main()
