"""Local Whisper engine wrappers. Every engine returns the same shape:

  [{"start": float, "end": float, "text": str,
    "avg_logprob": float|None, "no_speech_prob": float|None,
    "compression_ratio": float|None,
    "words": [{"start": float, "end": float, "word": str}, ...] }]

All engines run locally, no API key, no audio leaves the machine.

Model-size note (found by testing, not assumed): running two DIFFERENT-SIZE
models is what actually surfaces disagreement on ambiguous audio. Two
same-size models (e.g. mlx "base" vs openai "base") tend to make the exact
same mistake, because they're trained the same way at the same capacity —
cross-checking them proves almost nothing. A small model vs a medium model
on the same clip, by contrast, diverges exactly on the words the small model
guessed at. That's why PRIMARY_MODEL and VERIFY_MODEL below are deliberately
different sizes of the same engine (or a different engine), not just
"engine A vs engine B" at matched size.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

from common import run, which, log

# small/medium: tested against a known sentence where base-vs-base agreed on the
# SAME wrong answer, base-vs-small disagreed but both were still wrong, and
# small-vs-medium disagreed AND medium got it right. Medium is the meaningful
# jump in this pipeline's testing, not just "bigger for the sake of it". Costs a
# one-time ~1.5GB download per engine; drop to base/small in a disk-constrained
# environment (see git history / SKILL.md for that tradeoff).
PRIMARY_MODEL = {"mlx": "mlx-community/whisper-small-mlx", "openai": "small"}
VERIFY_MODEL = {"mlx": "mlx-community/whisper-medium-mlx", "openai": "medium"}


def available_engines() -> list:
    out = []
    if which("mlx_whisper"):
        out.append("mlx")
    try:
        r = run([sys.executable, "-m", "whisper", "--help"], check=False)
        if r.returncode == 0:
            out.append("openai")
    except FileNotFoundError:
        pass
    if which("whisper-cli"):
        out.append("whispercpp")
    return out


def transcribe_mlx(audio_path: str, work_dir: Path, model: str = None, language: str = None) -> list:
    model = model or PRIMARY_MODEL["mlx"]
    work_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "mlx_whisper", audio_path, "--model", model,
        "--output-dir", str(work_dir), "--output-format", "json",
        "--word-timestamps", "True",
        # Found by testing on a real video: the default (True) conditions each
        # segment's decoding on the PREVIOUS segment's text. Once one window
        # hallucinates (a noisy/ambiguous 30s opening triggered a repeated-token
        # loop, "ॐ ॐ ॐ..."), every later segment conditions on that garbage and
        # the whole rest of a 25-minute video came out as the same loop. Turning
        # this off let each segment decode independently — everything after the
        # bad opening window transcribed as normal, coherent speech.
        "--condition-on-previous-text", "False",
    ]
    if language:
        cmd += ["--language", language]
    # Found by testing: a chunked run over a long video (500+ chunks) can hit a
    # chunk where the mlx_whisper subprocess just hangs (0% CPU, sleeping,
    # no output ever produced) — no exception, no exit, subprocess.run() with
    # no timeout blocks forever and stalls the whole pipeline. A per-chunk
    # timeout turns that into a catchable failure instead of an infinite hang.
    try:
        r = run(cmd, check=False, timeout=180)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"mlx_whisper hung and was killed after {e.timeout}s on {audio_path}") from e
    json_path = work_dir / (Path(audio_path).stem + ".json")
    if not json_path.is_file():
        raise RuntimeError(f"mlx_whisper produced no output (exit {r.returncode}): {r.stderr[-800:]}")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    return _normalize_openai_shape(data)


def transcribe_openai(audio_path: str, work_dir: Path, model: str = None, language: str = None) -> list:
    model = model or PRIMARY_MODEL["openai"]
    work_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "whisper", audio_path, "--model", model,
        "--output_dir", str(work_dir), "--output_format", "json",
        "--word_timestamps", "True", "--fp16", "False",
        "--condition_on_previous_text", "False",  # see transcribe_mlx for why
    ]
    if language:
        cmd += ["--language", language]
    try:
        r = run(cmd, check=False, timeout=180)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"openai-whisper hung and was killed after {e.timeout}s on {audio_path}") from e
    json_path = work_dir / (Path(audio_path).stem + ".json")
    if not json_path.is_file():
        raise RuntimeError(f"openai-whisper produced no output (exit {r.returncode}): {r.stderr[-800:]}")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    return _normalize_openai_shape(data)


def _normalize_openai_shape(data: dict) -> list:
    segments = []
    detected_language = data.get("language")
    for seg in data.get("segments", []):
        words = [{"start": w.get("start"), "end": w.get("end"), "word": w.get("word", "").strip()}
                 for w in seg.get("words", [])] if seg.get("words") else []
        segments.append({
            "start": seg["start"], "end": seg["end"], "text": seg["text"].strip(),
            "avg_logprob": seg.get("avg_logprob"),
            "no_speech_prob": seg.get("no_speech_prob"),
            "compression_ratio": seg.get("compression_ratio"),
            "detected_language": detected_language,
            "words": words,
        })
    return segments


def transcribe_whispercpp(audio_path: str, work_dir: Path, model_path: str, language: str = None) -> list:
    work_dir.mkdir(parents=True, exist_ok=True)
    out_prefix = work_dir / "whispercpp_out"
    cmd = ["whisper-cli", "-m", model_path, "-f", audio_path, "-oj", "-ojf", "-of", str(out_prefix), "-np"]
    if language:
        cmd += ["-l", language]
    run(cmd)
    json_path = Path(str(out_prefix) + ".json")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    segments = []
    for seg in data.get("transcription", []):
        segments.append({
            "start": _hms_to_sec(seg["timestamps"]["from"]),
            "end": _hms_to_sec(seg["timestamps"]["to"]),
            "text": seg.get("text", "").strip(),
            "avg_logprob": None,       # whisper.cpp's json-full doesn't expose this directly
            "no_speech_prob": None,
            "compression_ratio": None,
            "words": [],
        })
    return segments


def _hms_to_sec(ts: str) -> float:
    ts = ts.replace(",", ".")
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def transcribe(engine: str, audio_path: str, work_dir: Path, **kwargs) -> list:
    if engine == "mlx":
        return transcribe_mlx(audio_path, work_dir, **kwargs)
    if engine == "openai":
        return transcribe_openai(audio_path, work_dir, **kwargs)
    if engine == "whispercpp":
        return transcribe_whispercpp(audio_path, work_dir, **kwargs)
    raise ValueError(f"unknown engine: {engine}")


def _split_long_interval(start: float, end: float, max_chunk_duration: float) -> list:
    """A single VAD speech interval can itself run longer than max_chunk_duration
    (a fast talker or speech over background music with no detected pause) —
    found by testing: one real video had a 35s continuous interval with zero
    gaps, which the old merge-only logic passed through unsplit, defeating the
    reason chunking exists. Force-slices at even intervals when this happens;
    an arbitrary mid-speech cut is worse than a pause-aligned one, but still
    far better than handing Whisper a chunk long enough to drift on."""
    duration = end - start
    if duration <= max_chunk_duration:
        return [(start, end)]
    n = math.ceil(duration / max_chunk_duration)
    step = duration / n
    return [(start + i * step, start + (i + 1) * step) for i in range(n)]


def _build_chunks(speech_intervals: list, max_chunk_duration: float = 28.0, max_gap_to_merge: float = 2.0) -> list:
    """Groups VAD speech intervals into chunks close to Whisper's native ~30s
    training window, merging small gaps (a normal pause) but never crossing
    max_chunk_duration. Silence between chunks is simply not transcribed —
    there's nothing to say there, and skipping it also means Whisper is never
    even given the option to hallucinate onto it."""
    if not speech_intervals:
        return []
    chunks = []
    cur_start, cur_end = speech_intervals[0]
    for s, e in speech_intervals[1:]:
        if (s - cur_end) <= max_gap_to_merge and (e - cur_start) <= max_chunk_duration:
            cur_end = e
        else:
            chunks.extend(_split_long_interval(cur_start, cur_end, max_chunk_duration))
            cur_start, cur_end = s, e
    chunks.extend(_split_long_interval(cur_start, cur_end, max_chunk_duration))
    return chunks


def transcribe_chunked(engine: str, audio_path: str, work_dir: Path, speech_intervals: list, **kwargs) -> list:
    """Transcribes in short, VAD-bounded chunks instead of one call over the
    whole file — found by testing that Whisper's accuracy degrades over long
    single-pass audio ("long-form drift", a known limitation): the exact same
    ~60s of audio transcribed cleanly on its own but came out as repeated-token
    garbage when transcribed as part of one continuous 25-minute pass. Chunking
    on VAD speech boundaries keeps every call close to the length Whisper was
    actually trained on, and resets whatever internal state degrades over long
    audio for every chunk."""
    work_dir.mkdir(parents=True, exist_ok=True)
    chunks = _build_chunks(speech_intervals)
    all_segments = []
    pad = 0.3
    for i, (start, end) in enumerate(chunks):
        chunk_path = work_dir / f"chunk_{i:04d}.wav"
        offset = max(0.0, start - pad)
        run([
            "ffmpeg", "-y", "-ss", f"{offset:.3f}", "-to", f"{end + pad:.3f}",
            "-i", audio_path, "-ac", "1", "-ar", "16000", str(chunk_path),
        ])
        try:
            segs = transcribe(engine, str(chunk_path), work_dir / f"out_{i:04d}", **kwargs)
        except RuntimeError as e:
            # One bad/hung chunk (e.g. a timeout) shouldn't take down transcription
            # for the whole video — log it and move on, same as a silent gap.
            log(f"  chunk {i:04d} failed, skipping: {e}")
            segs = []
        finally:
            chunk_path.unlink(missing_ok=True)
        for s in segs:
            s["start"] += offset
            s["end"] += offset
            for w in s.get("words", []):
                if w.get("start") is not None:
                    w["start"] += offset
                if w.get("end") is not None:
                    w["end"] += offset
        all_segments.extend(segs)
    return all_segments
