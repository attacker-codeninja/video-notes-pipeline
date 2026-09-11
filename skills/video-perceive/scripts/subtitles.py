"""Transcript-source resolution, priority order (first hit wins):

  1. sidecar file      — a .srt/.vtt next to a local video file
  2. embedded track    — a subtitle stream muxed into the video container
  3. manual captions   — human-written, pulled by yt-dlp (URL sources only)
  4. auto captions     — platform auto-generated, pulled by yt-dlp
  5. (none — caller falls back to local Whisper)

Every path converges on the same normalized shape: a list of
{start, end, text} segments, tagged with where they came from.
"""
from __future__ import annotations

import re
from pathlib import Path

from common import run, ffprobe_streams, log


def _ts_to_sec(ts: str) -> float:
    ts = ts.replace(",", ".")
    parts = ts.split(":")
    parts = [float(p) for p in parts]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    h, m, s = parts
    return h * 3600 + m * 60 + s


_CUE_RE = re.compile(
    r"(\d{1,2}:\d{2}(?::\d{2})?[.,]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}(?::\d{2})?[.,]\d{1,3})"
)
_TAG_RE = re.compile(r"<[^>]+>")


_LANG_RE = re.compile(r"^Language:\s*([a-zA-Z-]+)", re.MULTILINE)


def parse_vtt_language(path: str) -> str | None:
    """VTT files from yt-dlp carry a `Language: en-US` header — real, stated
    metadata about the caption, not a guess. Used to tell Whisper what
    language to expect instead of letting it auto-detect from a 30-second
    window and potentially guess wrong (found by testing: mlx-whisper
    mis-detected an English tutorial as Hindi and produced garbage for the
    entire video — a caption's own language header sidesteps that failure
    mode whenever captions exist)."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    m = _LANG_RE.search(text)
    if not m:
        return None
    return m.group(1).split("-")[0].lower()  # "en-US" -> "en"


def parse_vtt_or_srt(path: str) -> list:
    """Minimal VTT/SRT parser — no external deps. Good enough for spoken-word
    captions; drops styling tags and cue settings.

    YouTube auto-captions use a "rolling" format found by testing: each cue's
    body can have a BLANK line before the real content (a lone placeholder
    line, seen on the very first cue of a file) — stopping body collection at
    the first blank line, which is normal for standard WebVTT cue separators,
    silently dropped that cue's actual text here. Body collection now runs
    until the next timestamp line (or EOF) instead, so a leading blank line is
    swallowed rather than treated as "end of cue.\""""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    segments = []
    i = 0
    while i < len(lines):
        m = _CUE_RE.search(lines[i])
        if m:
            start, end = _ts_to_sec(m.group(1)), _ts_to_sec(m.group(2))
            i += 1
            body = []
            while i < len(lines) and not _CUE_RE.search(lines[i]):
                body.append(lines[i])
                i += 1
            raw = " ".join(body).strip()
            clean = _TAG_RE.sub("", raw).strip()
            clean = " ".join(clean.split())  # collapse the internal whitespace left by blank body lines
            if clean:
                # de-dupe identical consecutive cues (common in rolling auto-captions)
                if segments and segments[-1]["text"] == clean:
                    segments[-1]["end"] = end
                else:
                    segments.append({"start": start, "end": end, "text": clean})
        else:
            i += 1
    return _drop_rolling_artifacts(segments)


def _drop_rolling_artifacts(segments: list, max_artifact_duration: float = 1.0) -> list:
    """YouTube's rolling-caption format hands off between windows via a very
    short (often ~10ms) cue whose text is just the tail end of what the
    previous/next cue already shows in full — found by testing: 308 of 1700
    segments in a real 34-minute auto-captioned video were these handoff
    artifacts, each under 20ms long, each one a substring of an adjacent kept
    segment. They carry no information the surrounding segments don't already
    have, but their near-zero duration made the audio cross-check flag them
    as "no speech detected" — a false alarm about the pipeline's own caption
    parsing, not about the video. Dropping them loses no transcript content."""
    out = []
    for i, seg in enumerate(segments):
        dur = seg["end"] - seg["start"]
        if dur <= max_artifact_duration:
            prev_text = segments[i - 1]["text"] if i > 0 else ""
            next_text = segments[i + 1]["text"] if i + 1 < len(segments) else ""
            if seg["text"] and (seg["text"] in prev_text or seg["text"] in next_text):
                continue
        out.append(seg)
    return out


def find_sidecar(video_path: str) -> str | None:
    p = Path(video_path)
    for ext in (".vtt", ".srt"):
        candidate = p.with_suffix(ext)
        if candidate.is_file():
            return str(candidate)
    return None


def find_embedded_track(video_path: str, out_dir: Path) -> str | None:
    try:
        info = ffprobe_streams(video_path)
    except Exception:
        return None
    sub_streams = [s for s in info.get("streams", []) if s.get("codec_type") == "subtitle"]
    if not sub_streams:
        return None
    idx = sub_streams[0]["index"]
    out_path = out_dir / "embedded_track.vtt"
    result = run([
        "ffmpeg", "-y", "-i", video_path, "-map", f"0:{idx}", str(out_path),
    ], check=False)
    if result.returncode == 0 and out_path.is_file() and out_path.stat().st_size > 0:
        return str(out_path)
    return None


def resolve(video_path: str, out_dir: Path, manual_captions: list, auto_captions: list) -> dict | None:
    """Returns {"source": <tag>, "segments": [...], "language": <code-or-None>} or None."""
    sidecar = find_sidecar(video_path)
    if sidecar:
        log(f"transcript source: sidecar ({sidecar})")
        return {"source": f"sidecar_{Path(sidecar).suffix.lstrip('.')}",
                "segments": parse_vtt_or_srt(sidecar), "language": parse_vtt_language(sidecar)}

    embedded = find_embedded_track(video_path, out_dir)
    if embedded:
        log("transcript source: embedded subtitle track")
        return {"source": "embedded_track", "segments": parse_vtt_or_srt(embedded),
                "language": parse_vtt_language(embedded)}

    if manual_captions:
        log(f"transcript source: manual captions ({manual_captions[0]})")
        return {"source": "manual_caption", "segments": parse_vtt_or_srt(manual_captions[0]),
                "language": parse_vtt_language(manual_captions[0])}

    if auto_captions:
        log(f"transcript source: auto captions ({auto_captions[0]})")
        return {"source": "auto_caption", "segments": parse_vtt_or_srt(auto_captions[0]),
                "language": parse_vtt_language(auto_captions[0])}

    log("no caption source found — will fall back to local Whisper")
    return None
