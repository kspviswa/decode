#!/usr/bin/env python3
"""Decode daily podcast generator — KOKORO TTS variant (local, no cloud).

Reads a dialogue script (work/podcast_script.json) and synthesizes a two-host
podcast with local kokoro-tts (kokoro_onnx + v1.0 models), concatenating turns
with small silences via ffmpeg.

Run with the shravana venv python (it has kokoro_onnx + onnxruntime):
  /home/kspviswa/portals/shravana/.venv/bin/python scripts/make_podcast_kokoro.py \
      --out posts/<YYYY-MM-DD>/podcast.mp3

Script JSON schema (same as edge-tts variant):
{
  "title": "Optional title",
  "lines": [
    {"speaker": "avery"|"jordan", "text": "...", "gap_after": 0.5}
  ]
}

Hosts & voices (Kokoro v1.0 pack, en-us):
  avery  -> af_heart   (female, expressive)
  jordan -> am_michael (male)
"""
import argparse, json, os, subprocess, sys, tempfile, wave

# tts_kokoro.py lives in ~/portals/shravana (reused wholesale — same backend
# the Shravana audiobook portal uses in production).
SHRAVANA_DIR = "/home/kspviswa/portals/shravana"
MODELS_DIR = os.path.join(SHRAVANA_DIR, "models")
sys.path.insert(0, SHRAVANA_DIR)

from tts_kokoro import KokoroOnnxBackend, SAMPLE_RATE  # noqa: E402

VOICES = {
    "avery": "af_heart",
    "jordan": "am_michael",
}
DEFAULT_GAP = 0.5  # seconds between turns


def write_wav(path, pcm_bytes):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(bytes(pcm_bytes))


def synth_line(backend, voice, text, out_wav, speed=1.0):
    pcm = backend.synthesize(text, voice=voice, speed=speed)
    write_wav(out_wav, pcm)


def make_silence(duration, out_wav):
    write_wav(out_wav, b"\x00\x00" * int(SAMPLE_RATE * duration))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", default="work/podcast_script.json")
    ap.add_argument("--out", default="podcast.mp3")
    ap.add_argument("--speed", type=float, default=1.0)
    args = ap.parse_args()

    with open(args.script) as f:
        script = json.load(f)
    lines = script["lines"]
    print("Loading kokoro model (arm64 CPU)...", flush=True)
    backend = KokoroOnnxBackend(
        os.path.join(MODELS_DIR, "kokoro-v1.0.onnx"),
        os.path.join(MODELS_DIR, "voices-v1.0.bin"),
    )
    print(f"Generating {len(lines)} turns with kokoro...", flush=True)

    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        concat_list = os.path.join(tmp, "concat.txt")
        for i, line in enumerate(lines):
            speaker = line.get("speaker", "avery").lower()
            voice = VOICES.get(speaker, VOICES["avery"])
            seg = os.path.join(tmp, f"seg_{i:03d}.wav")
            synth_line(backend, voice, line["text"], seg, args.speed)
            parts.append(seg)

            gap = line.get("gap_after", DEFAULT_GAP)
            if gap > 0 and i < len(lines) - 1:
                sil = os.path.join(tmp, f"sil_{i:03d}.wav")
                make_silence(gap, sil)
                parts.append(sil)
            if (i + 1) % 5 == 0 or i == len(lines) - 1:
                print(f"  {i+1}/{len(lines)} turns", flush=True)

        with open(concat_list, "w") as f:
            for p in parts:
                f.write(f"file '{p}'\n")

        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
               "-c:a", "libmp3lame", "-b:a", "96k", args.out]
        subprocess.run(cmd, check=True, capture_output=True)

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