"""Mechanical frame<->transcript cross-check via on-screen text.

Uses the `tesseract` CLI directly (no pytesseract, no new pip installs — this
machine already has the `tesseract` binary via Homebrew). This is a real,
independent third signal alongside audio-silence detection and multi-model
transcript comparison: if a flagged segment's transcript text shares a
distinctive word with text actually printed on the matching frame (a slide,
a caption, code, a name on screen), that's mechanical corroboration Claude
doesn't have to go re-derive by eye for every flagged line.

This is a hint, not a verdict — OCR on a non-text video frame will usually
just find nothing (reported honestly as no signal), and stylized/handwritten
text can still fool it. Claude's own frame read at Layer 2 is still what
resolves ambiguity when OCR has nothing to say.
"""
from __future__ import annotations

from common import run, which


def available() -> bool:
    return which("tesseract") is not None


def read_text(image_path: str) -> str:
    if not available():
        return ""
    r = run(["tesseract", image_path, "stdout", "--psm", "6"], check=False)
    if r.returncode != 0:
        return ""
    return r.stdout.strip()


def nearest_frames(frame_records: list, start: float, end: float, pad: float = 2.0) -> list:
    return [f for f in frame_records if (start - pad) <= f["timestamp_sec"] <= (end + pad)]


def shares_distinctive_word(a: str, b: str, min_len: int = 4) -> str | None:
    """Returns the shared word if the OCR text and a transcript candidate share
    a word long enough to not be a coincidence (skips short common words)."""
    a_words = {w.strip(".,!?:;\"'()").lower() for w in a.split() if len(w) >= min_len}
    b_words = {w.strip(".,!?:;\"'()").lower() for w in b.split() if len(w) >= min_len}
    hit = a_words & b_words
    return next(iter(hit), None)
