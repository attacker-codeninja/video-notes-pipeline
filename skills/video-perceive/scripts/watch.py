#!/usr/bin/env python3
"""video-perceive — turn a video into structured evidence (frames, full audio,
multi-source cross-checked transcript) for Claude to read. This is an INPUT
layer only: it does not summarize, interpret, or write notes. See SKILL.md.

Source can be a single video URL/path, a playlist URL, or a channel/user URL —
download.expand_source() resolves any of these into one or more individual
video URLs, and each one gets the exact same per-video pipeline below, into
its own subfolder. All of this is Layer 1 — mechanical, zero Claude tokens,
regardless of whether it's 1 video or 200.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import audio as audio_mod
import download
import frames as frames_mod
import manifest as manifest_mod
import transcribe
import vad
from common import log, write_json, is_url


def parse_args():
    p = argparse.ArgumentParser(description="video-perceive: video -> frames + audio + transcript")
    p.add_argument("source", help="video URL or local file path")
    p.add_argument("-o", "--out", default="crv-out", help="output directory")
    p.add_argument("--overwrite", action="store_true", help="replace an existing analysis in --out")
    p.add_argument("--cookies", default=None, help="cookies file for gated yt-dlp sources (your own, authorized access)")
    p.add_argument("--limit", type=int, default=None,
                   help="for a playlist/channel source, only process up through this position "
                        "(bounds the yt-dlp listing itself via --playlist-end, not just "
                        "the resulting list). Combine with --start to do a channel in batches. "
                        "Ignored for a single video or local file.")
    p.add_argument("--start", type=int, default=None,
                   help="for a playlist/channel source, start at this 1-indexed position "
                        "(--playlist-start) instead of the first video — e.g. --start 11 --limit 20 "
                        "processes entries 11-20 without touching the first 10. Ignored for a "
                        "single video or local file.")
    p.add_argument("--scene", type=float, default=0.30, help="scene-change sensitivity (lower = more frames)")
    p.add_argument("--fps-floor", type=float, default=2.0, help="guarantee a candidate frame at least every N seconds")
    p.add_argument("--max-frames", type=int, default=None,
                   help="optional hard cap on kept frames. Default is uncapped — frame count is "
                        "governed by actual scene changes + density floor, not video length. Only "
                        "set this if you deliberately want a lighter/faster pass.")
    p.add_argument("--resolution", type=int, default=512, help="frame width in px")
    p.add_argument("--dedup-threshold", type=float, default=8.0, help="%% of pixels changed (global channel) to count as new")
    p.add_argument("--regional-threshold", type=float, default=35.0, help="%% of a single grid cell changed (regional channel) to count as new")
    p.add_argument("--dedup-window", type=int, default=4, help="compare against the last N kept frames")
    p.add_argument("--grid", action="store_true", help="also tile frames into 3x3 contact sheets")
    p.add_argument("--no-transcribe", action="store_true", help="skip transcript entirely")
    p.add_argument("--engine", choices=["mlx", "openai", "whispercpp"], default=None,
                   help="preferred Whisper engine (default: first available)")
    p.add_argument("--fast", action="store_true",
                   help="single-pass transcription only (skip the larger-model verification pass). "
                        "Faster, but confident wrong transcriptions won't get caught.")
    p.add_argument("--language", default=None,
                   help="ISO 639-1 code (e.g. 'en', 'hi') to force for Whisper instead of "
                        "auto-detection. Auto-detection uses only the first ~30s of audio and "
                        "can guess wrong (tested: mis-detected an English video as Hindi and "
                        "produced garbage for the whole thing). If captions exist, their own "
                        "stated language is used automatically unless this overrides it.")
    return p.parse_args()


def _slugify(text: str | None, fallback: str) -> str:
    if not text:
        return fallback
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")
    return slug[:80] or fallback


def process_one(source: str, out_dir: Path, args) -> dict:
    """Runs the full per-video Layer 1 pipeline (download, frames, audio, VAD,
    transcript, manifest) for a single video into out_dir. Returns a short
    status dict — used directly for single-video runs, and collected into
    INDEX.txt for playlist/channel runs. No Claude/LLM call anywhere in here."""
    out_dir.mkdir(parents=True, exist_ok=True)

    log(f"source: {source}")
    fetched = download.fetch(source, out_dir, cookies=args.cookies)
    video_path = fetched["video_path"]
    log(f"video: {video_path}")

    log("extracting frames...")
    frame_result = frames_mod.extract_frames(
        video_path, out_dir,
        scene_threshold=args.scene, fps_floor=args.fps_floor,
        max_frames=args.max_frames, resolution=args.resolution,
        dedup_threshold=args.dedup_threshold, dedup_window=args.dedup_window,
        regional_threshold=args.regional_threshold, make_grid=args.grid,
    )
    log(f"kept {len(frame_result['frames'])} frames" + (f", {len(frame_result['grids'])} grids" if args.grid else ""))

    log("extracting audio...")
    audio_info = audio_mod.extract(video_path, out_dir)

    # VAD runs BEFORE transcription, not just as a post-hoc cross-check — its
    # speech intervals are what Whisper chunks on (see transcribe.py /
    # whisper_engines.transcribe_chunked). Found by testing: feeding Whisper an
    # entire long file in one call causes real "long-form drift" — the exact
    # same audio transcribed cleanly in isolation but degraded into repeated-
    # token garbage partway through a 25-minute single pass. Chunking on VAD-
    # detected speech keeps every Whisper call close to the ~30s window it was
    # actually trained on, which also means the same speech_intervals serve
    # double duty here and in apply_mechanical_crosschecks below — computed once.
    speech_intervals = []
    if audio_info.get("audio_16k_path"):
        if vad.available():
            log("running voice-activity detection (used for both Whisper chunking and the audio cross-check)...")
            try:
                speech_intervals = vad.detect_speech(audio_info["audio_16k_path"])
            except Exception as e:
                log(f"  VAD failed ({e}) — Whisper will run as a single whole-file pass instead of chunked, "
                    f"which is more prone to long-form drift on long audio; voice-activity cross-check skipped")
        else:
            log("torch/torchaudio not available — Whisper will run as a single whole-file pass instead of "
                "chunked, which is more prone to long-form drift on long audio; voice-activity cross-check skipped")

    log("resolving transcript...")
    segments = transcribe.build_transcript(
        video_path, out_dir,
        manual_captions=fetched["manual_captions"], auto_captions=fetched["auto_captions"],
        translation_manual_captions=fetched.get("translation_manual_captions", []),
        translation_auto_captions=fetched.get("translation_auto_captions", []),
        audio_16k_path=audio_info.get("audio_16k_path"),
        engine_pref=args.engine, no_transcribe=args.no_transcribe,
        fast=args.fast, language=args.language or fetched.get("spoken_language"),
        speech_intervals=speech_intervals,
    )
    log(f"transcript: {len(segments)} segments")

    if segments and speech_intervals:
        log("cross-checking transcript against voice-activity detection + on-screen text...")
        frames_abs = [{"file": str(out_dir / f["file"]), "timestamp_sec": f["timestamp_sec"]}
                      for f in frame_result["frames"]]
        transcribe.apply_mechanical_crosschecks(segments, frames_abs, speech_intervals)
        mismatches = sum(1 for s in segments if "no_speech_detected" in str(s.get("audio_check", "")))
        if mismatches:
            log(f"  {mismatches} segment(s) have almost no detected voice activity")

    write_json(out_dir / "frames.json", frame_result["frames"])
    write_json(out_dir / "transcript.json", segments)
    (out_dir / "transcript.txt").write_text(transcribe.render_txt(segments), encoding="utf-8")

    manifest_mod.write(
        out_dir, video_path, frame_result["duration_sec"],
        frame_result["frames"], frame_result["grids"], audio_info, segments,
    )

    return {
        "source": source, "out_dir": str(out_dir), "video_path": video_path,
        "duration_sec": frame_result["duration_sec"],
        "frames": len(frame_result["frames"]), "segments": len(segments),
    }


def main():
    args = parse_args()
    out_dir = Path(args.out).expanduser().resolve()

    if out_dir.exists() and any(out_dir.iterdir()):
        if not args.overwrite:
            print(f"ERROR: {out_dir} is non-empty. Pass --overwrite to replace it, or use a fresh -o.", file=sys.stderr)
            sys.exit(1)
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not is_url(args.source):
        # Local file — always exactly one video, no expansion needed.
        process_one(args.source, out_dir, args)
        print(f"\ndone -> {out_dir}")
        print(f"start with: {out_dir / 'MANIFEST.txt'}")
        return

    log(f"resolving source (single video / playlist / channel): {args.source}")
    entries = download.expand_source(args.source, cookies=args.cookies, limit=args.limit, start=args.start)

    if len(entries) == 1:
        # A single video URL resolves to exactly one entry — keep the flat,
        # no-subfolder layout so existing single-video usage is unaffected.
        process_one(entries[0]["url"], out_dir, args)
        print(f"\ndone -> {out_dir}")
        print(f"start with: {out_dir / 'MANIFEST.txt'}")
        return

    log(f"source expanded to {len(entries)} videos — running Layer 1 on each into its own subfolder")
    results = []
    first_num = args.start or 1
    for offset, entry in enumerate(entries):
        i = first_num + offset  # folder numbers reflect true playlist position, so batches don't collide
        slug = _slugify(entry.get("title") or entry.get("id"), f"video_{i:03d}")
        video_out = out_dir / f"{i:03d}_{slug}"
        log(f"[{offset + 1}/{len(entries)}] {entry['url']} -> {video_out}")
        try:
            r = process_one(entry["url"], video_out, args)
            r["status"] = "done"
        except Exception as e:
            log(f"  FAILED: {e}")
            r = {"source": entry["url"], "out_dir": str(video_out), "status": "failed", "error": str(e)}
        results.append(r)

    index_lines = [f"video-perceive batch — {len(entries)} videos from: {args.source}", ""]
    for r in results:
        if r["status"] == "done":
            index_lines.append(
                f"[done]   {r['out_dir']}  ({r['segments']} transcript segments, "
                f"{r['frames']} frames, {r['duration_sec']:.0f}s) <- {r['source']}"
            )
        else:
            index_lines.append(f"[FAILED] {r['out_dir']}  {r['error']} <- {r['source']}")
    (out_dir / "INDEX.txt").write_text("\n".join(index_lines) + "\n", encoding="utf-8")

    done = sum(1 for r in results if r["status"] == "done")
    print(f"\ndone -> {out_dir} ({done}/{len(entries)} videos succeeded)")
    print(f"start with: {out_dir / 'INDEX.txt'}")


if __name__ == "__main__":
    main()
