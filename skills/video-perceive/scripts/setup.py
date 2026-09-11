"""Preflight check for video-perceive. Reports what's installed and what's missing.

Exit codes:
  0 = ready (ffmpeg/ffprobe/yt-dlp present; at least one local transcription
      path available, or user is fine with captions-only)
  2 = missing required binaries (ffmpeg/ffprobe/yt-dlp)

This script never installs anything on its own — it only reports, so the
skill can decide what to tell the user. Run with --json for a machine-readable
report, or with no args for a human-readable one.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from common import which, run


def find_whispercpp_model() -> str | None:
    """A ggml model isn't bundled with whisper-cpp. Look in the usual places;
    return None if nothing is found (the engine is then reported unavailable,
    not an error — it's an optional cross-check engine, not a required one)."""
    import os
    env = os.environ.get("WHISPER_CPP_MODEL")
    if env and Path(env).is_file():
        return env
    candidates = [
        Path.home() / ".cache" / "whisper-cpp",
        Path.home() / "whisper.cpp" / "models",
        Path("/opt/homebrew/share/whisper-cpp"),
    ]
    for d in candidates:
        if d.is_dir():
            hits = sorted(d.glob("ggml-*.bin"))
            if hits:
                return str(hits[0])
    return None


def check() -> dict:
    report = {
        "ffmpeg": which("ffmpeg") is not None,
        "ffprobe": which("ffprobe") is not None,
        "yt_dlp": which("yt-dlp") is not None,
        "engines": {},
    }

    if which("mlx_whisper"):
        report["engines"]["mlx"] = {"available": True, "note": "Apple Silicon, auto-downloads model on first use"}
    else:
        report["engines"]["mlx"] = {"available": False}

    try:
        r = run([sys.executable, "-m", "whisper", "--help"], check=False)
        report["engines"]["openai"] = {"available": r.returncode == 0}
    except FileNotFoundError:
        report["engines"]["openai"] = {"available": False}

    cpp_model = find_whispercpp_model()
    if which("whisper-cli"):
        report["engines"]["whispercpp"] = {
            "available": cpp_model is not None,
            "binary_found": True,
            "model_found": cpp_model is not None,
            "model_path": cpp_model,
        }
        if cpp_model is None:
            report["engines"]["whispercpp"]["note"] = (
                "whisper-cli installed but no ggml model found. Download one from "
                "https://huggingface.co/ggerganov/whisper.cpp and set $WHISPER_CPP_MODEL, "
                "or skip it — mlx/openai engines are enough."
            )
    else:
        report["engines"]["whispercpp"] = {"available": False}

    any_local_engine = any(e.get("available") for e in report["engines"].values())
    report["any_local_engine"] = any_local_engine
    report["ready"] = report["ffmpeg"] and report["ffprobe"] and report["yt_dlp"]

    try:
        import torch, torchaudio  # noqa: F401
        report["vad"] = {"available": True}
    except ImportError:
        report["vad"] = {"available": False, "note": "pip install torchaudio (torch already comes with openai-whisper) for the voice-activity cross-check"}

    report["ocr"] = {"available": which("tesseract") is not None}
    if not report["ocr"]["available"]:
        report["ocr"]["note"] = "brew install tesseract for the frame on-screen-text cross-check"

    free_gb = shutil.disk_usage(str(Path.home())).free / (1024 ** 3)
    report["disk_free_gb"] = round(free_gb, 2)
    report["disk_low"] = free_gb < 2.0  # a medium Whisper model alone is ~1.5GB
    return report


def main() -> int:
    report = check()
    if "--json" in sys.argv:
        print(json.dumps(report, indent=2))
    else:
        for k in ("ffmpeg", "ffprobe", "yt_dlp"):
            print(f"{k}: {'OK' if report[k] else 'MISSING'}")
        for name, info in report["engines"].items():
            print(f"whisper[{name}]: {'available' if info.get('available') else 'unavailable'}"
                  + (f" ({info['note']})" if info.get("note") else ""))
        print(f"voice-activity detection (VAD): {'available' if report['vad']['available'] else 'unavailable'}"
              + (f" ({report['vad']['note']})" if report['vad'].get("note") else ""))
        print(f"frame OCR (tesseract): {'available' if report['ocr']['available'] else 'unavailable'}"
              + (f" ({report['ocr']['note']})" if report['ocr'].get("note") else ""))
        if not report["ready"]:
            print("\nMissing required binaries. Install with:")
            print("  macOS:  brew install ffmpeg yt-dlp")
            print("  Linux:  sudo apt install ffmpeg && pipx install yt-dlp")
        elif not report["any_local_engine"]:
            print("\nNo local Whisper engine found. Captions-only videos will still work.")
            print("For no-caption videos, install one of: mlx-whisper, openai-whisper, whisper-cpp.")
        print(f"\ndisk free: {report['disk_free_gb']} GB")
        if report["disk_low"]:
            print("WARNING: low disk space. Whisper model downloads (150MB-1.5GB+) and video")
            print("downloads can fail mid-way with 'No space left on device' — free up space")
            print("before running on a video that needs a model not already cached.")
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    sys.exit(main())
