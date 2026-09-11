"""Audio is a first-class output, not a throwaway intermediate for Whisper.

Produces two files:
  audio.m4a      — full original soundtrack, kept for the record (music, tone,
                   sound effects — everything a transcript can't capture).
                   Copied losslessly when the source codec allows it.
  audio_16k.wav  — mono 16kHz, the format every local Whisper engine wants.
                   Derived from audio.m4a, not the other way around.
"""
from __future__ import annotations

from pathlib import Path

from common import run, log


def extract(video_path: str, out_dir: Path) -> dict:
    has_audio = _has_audio_stream(video_path)
    result = {"has_audio": has_audio, "audio_path": None, "audio_16k_path": None}
    if not has_audio:
        log("no audio stream in source — skipping audio extraction")
        return result

    full_path = out_dir / "audio.m4a"
    r = run(["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "copy", str(full_path)], check=False)
    if r.returncode != 0 or not full_path.is_file():
        log("audio codec copy failed, re-encoding to AAC instead")
        run(["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "aac", "-b:a", "192k", str(full_path)])
    result["audio_path"] = str(full_path)

    wav_path = out_dir / "audio_16k.wav"
    run(["ffmpeg", "-y", "-i", str(full_path), "-vn", "-ac", "1", "-ar", "16000", str(wav_path)])
    result["audio_16k_path"] = str(wav_path)
    return result


def _has_audio_stream(video_path: str) -> bool:
    from common import ffprobe_streams
    try:
        info = ffprobe_streams(video_path)
    except Exception:
        return False
    return any(s.get("codec_type") == "audio" for s in info.get("streams", []))
