"""Shared helpers for the video-perceive pipeline."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


def log(msg: str) -> None:
    print(f"[video-perceive] {msg}", file=sys.stderr)


def which(name: str) -> str | None:
    return shutil.which(name)


def run(cmd: list, **kwargs) -> subprocess.CompletedProcess:
    """Run a command, capturing output. Raises on non-zero exit unless check=False.
    errors="replace" because some external tools (tesseract, yt-dlp, ffmpeg on some
    locales) occasionally emit a stray non-UTF-8 byte on stderr — that shouldn't
    crash the whole pipeline over a log line we don't even need to parse exactly."""
    check = kwargs.pop("check", True)
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace", check=check, **kwargs) \
        if check else subprocess.run(cmd, capture_output=True, text=True, errors="replace", **kwargs)


def ffprobe_duration(path: str) -> float:
    out = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", path,
    ])
    data = json.loads(out.stdout)
    return float(data["format"]["duration"])


def ffprobe_streams(path: str) -> dict:
    out = run([
        "ffprobe", "-v", "error", "-show_streams", "-of", "json", path,
    ])
    return json.loads(out.stdout)


def fmt_ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    if h:
        return f"{h:02d}:{m:02d}:{s:05.2f}"
    return f"{m:02d}:{s:05.2f}"


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def is_url(source: str) -> bool:
    return source.startswith("http://") or source.startswith("https://")
