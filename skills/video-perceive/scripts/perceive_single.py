#!/usr/bin/env python3
"""perceive_single.py -- packages one video-perceive run (watch.py) into the
folder layout video-summary expects: ./<upload-date>_<title-slug>/_layer1/,
named and dated from the video's own metadata (fetched separately, before
download, via one cheap yt-dlp --dump-json call). Falls back to a plain
./_layer1 if metadata fetch fails (e.g. the source is a local file path).

After a successful run, the video's URL/author/title/upload-date get
prepended to MANIFEST.txt, and _layer1/ is stripped down to only what
video-summary (Layer 2) needs: frames/, frames.json, MANIFEST.txt,
native_auto_captions.vtt, transcript.json, transcript.txt -- source.mp4,
audio.m4a, audio_16k.wav, and any leftover download/ directory are deleted.

This is the single-video convenience path. For a playlist/channel source, or
for custom output locations, call scripts/watch.py directly instead (see
SKILL.md) -- this script intentionally does not do batch/channel tracking;
that's video-flow's job, one level up.

Usage: python3 perceive_single.py <url-or-path> [--grid]
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

WATCH_SCRIPT = Path(__file__).resolve().parent / "watch.py"
STRIP_CHARS = ["'", "’", ",", "$"]  # dropped entirely, not turned into a hyphen

# What video-summary (Layer 2) actually needs from a finished _layer1 --
# everything else (source.mp4, audio.m4a, audio_16k.wav, any download/ dir,
# ...) gets deleted once this script's own job (perceive + metadata stamp) is
# done.
KEEP_IN_LAYER1 = {
    "frames", "frames.json", "MANIFEST.txt",
    "native_auto_captions.vtt", "transcript.json", "transcript.txt",
}


def die(msg: str):
    print(msg, file=sys.stderr)
    sys.exit(1)


def date_slugify(title: str) -> str:
    s = title.lower()
    for ch in STRIP_CHARS:
        s = s.replace(ch, "")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def fetch_single_metadata(url: str) -> dict:
    """One yt-dlp --dump-json call -- no download. Raises on failure (caller
    decides the fallback); works for a single video URL, not a channel/playlist."""
    out = subprocess.run(
        ["yt-dlp", "--dump-json", "--no-playlist", url],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(out.stdout.splitlines()[0])
    return {
        "url": data.get("webpage_url") or url,
        "author": data.get("uploader") or data.get("channel") or "",
        "title": data.get("title") or "",
        "upload_date": data.get("upload_date") or "",  # YYYYMMDD, may be empty
    }


def format_upload_date(upload_date: str) -> str:
    if len(upload_date) == 8 and upload_date.isdigit():
        return f"{upload_date[0:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
    return datetime.now().strftime("%Y-%m-%d")  # fallback: today, video had none


def write_metadata_header(layer1_dir: Path, meta: dict, date_str: str):
    """Prepend url/author/title/date to MANIFEST.txt -- kept in the retained
    file set, so video-summary can read it later without a separate metadata
    file."""
    manifest = layer1_dir / "MANIFEST.txt"
    header = (
        f"video_url: {meta['url']}\n"
        f"video_author: {meta['author']}\n"
        f"video_title: {meta['title']}\n"
        f"video_upload_date: {date_str}\n"
        + "-" * 40 + "\n"
    )
    existing = manifest.read_text() if manifest.exists() else ""
    manifest.write_text(header + existing)


def cleanup_layer1(layer1_dir: Path):
    """Strip a finished _layer1 down to KEEP_IN_LAYER1 -- drops source.mp4,
    audio.m4a, audio_16k.wav, any leftover download/ dir, etc."""
    for entry in layer1_dir.iterdir():
        if entry.name in KEEP_IN_LAYER1:
            continue
        if entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)
        else:
            entry.unlink(missing_ok=True)


def main():
    if len(sys.argv) < 2:
        die("Usage: perceive_single.py <url-or-path> [--grid]")
    url = sys.argv[1]
    extra_flags = sys.argv[2:]  # e.g. --grid, passed straight through to watch.py

    if not WATCH_SCRIPT.exists():
        die(f"watch.py not found at {WATCH_SCRIPT} -- expected it next to this script.")

    meta = None
    try:
        print("[perceive_single] fetching video metadata...")
        meta = fetch_single_metadata(url)
    except (subprocess.CalledProcessError, json.JSONDecodeError, IndexError) as e:
        print(f"[perceive_single] warning: metadata fetch failed ({e}); using plain ./_layer1", file=sys.stderr)

    date_str = None
    if meta:
        date_str = format_upload_date(meta["upload_date"])
        slug = date_slugify(meta["title"]) or "untitled"
        layer1_dir = Path.cwd() / f"{date_str}_{slug}" / "_layer1"
    else:
        layer1_dir = Path.cwd() / "_layer1"

    layer1_dir.mkdir(parents=True, exist_ok=True)
    print(f"[perceive_single] -> {layer1_dir}")

    cmd = ["python3", str(WATCH_SCRIPT), url, "-o", str(layer1_dir), *extra_flags]
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(result.returncode)  # leave partial output as-is for debugging

    if meta:
        write_metadata_header(layer1_dir, meta, date_str)
    cleanup_layer1(layer1_dir)
    print(f"[perceive_single] done -> {layer1_dir}")


if __name__ == "__main__":
    main()
