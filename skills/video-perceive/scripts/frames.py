"""Scene-aware frame extraction + dedup.

Two-pass candidate generation (both bounded by duration, so cost is
predictable regardless of what's actually in the video):
  Pass A — scene-change timestamps from ffmpeg's own scene-detection filter.
  Pass B — a density floor: at least one candidate every `fps_floor` seconds,
           so a slow static screencast still gets sampled.

Then a two-channel dedup pass over the sliding window of the last
`dedup_window` KEPT frames:
  - global channel   — % of downscaled pixels that changed. Catches ordinary
                        cuts and big visual changes.
  - regional channel — the frame is split into a grid; if any single cell
                        changed sharply even though the global average did
                        not, the frame is kept anyway. This is what catches a
                        small moving subject (a cursor, a person in the
                        corner) or a localized change (caption swap, one line
                        of code edited) that a whole-frame average would
                        wash out.

This is a simplified, from-scratch version of the idea — not a port of any
specific tool's algorithm.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
from PIL import Image

from common import run, ffprobe_duration, fmt_ts, log

_SCENE_RE = re.compile(r"pts_time:([\d.]+)")


def _scene_change_timestamps(video_path: str, threshold: float) -> list:
    r = run([
        "ffmpeg", "-i", video_path,
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-vsync", "vfr", "-f", "null", "-",
    ], check=False)
    return [float(m) for m in _SCENE_RE.findall(r.stderr)]


def _floor_timestamps(duration: float, fps_floor: float) -> list:
    ts = []
    t = 0.0
    while t < duration:
        ts.append(round(t, 3))
        t += fps_floor
    ts.append(max(0.0, duration - 0.05))  # always try to capture the closing frame
    return ts


def _extract_at(video_path: str, timestamps: list, tmp_dir: Path, resolution: int) -> list:
    """One accurate seek per timestamp. Returns [(timestamp, Path)]."""
    out = []
    for i, t in enumerate(timestamps):
        dest = tmp_dir / f"cand_{i:05d}.jpg"
        r = run([
            "ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", video_path,
            "-frames:v", "1", "-vf", f"scale={resolution}:-2",
            "-q:v", "3", str(dest),
        ], check=False)
        if r.returncode == 0 and dest.is_file():
            out.append((t, dest))
    return out


def _load_small(path: Path, size=(64, 36)) -> np.ndarray:
    img = Image.open(path).convert("RGB").resize(size)
    return np.asarray(img, dtype=np.float32)


def _grid_diff_max(a: np.ndarray, b: np.ndarray, cells=(6, 6)) -> float:
    h, w, _ = a.shape
    ch, cw = h // cells[0], w // cells[1]
    max_pct = 0.0
    for i in range(cells[0]):
        for j in range(cells[1]):
            ca = a[i * ch:(i + 1) * ch, j * cw:(j + 1) * cw]
            cb = b[i * ch:(i + 1) * ch, j * cw:(j + 1) * cw]
            if ca.size == 0:
                continue
            diff = np.abs(ca - cb).mean(axis=-1)
            pct = float((diff > 25).mean()) * 100
            max_pct = max(max_pct, pct)
    return max_pct


def _global_diff_pct(a: np.ndarray, b: np.ndarray) -> float:
    diff = np.abs(a - b).mean(axis=-1)
    return float((diff > 25).mean()) * 100


def dedup(candidates: list, dedup_threshold: float, dedup_window: int, regional_threshold: float) -> list:
    """candidates: [(timestamp, Path)] in chronological order. Returns the kept subset."""
    kept = []
    kept_small = []
    for t, path in candidates:
        small = _load_small(path)
        if not kept_small:
            kept.append((t, path, "first_frame"))
            kept_small.append(small)
            continue

        window = kept_small[-dedup_window:]
        global_pct = max(_global_diff_pct(small, w) for w in window)
        regional_pct = min(_grid_diff_max(small, w) for w in window)

        if global_pct >= dedup_threshold:
            kept.append((t, path, "global_change"))
            kept_small.append(small)
        elif regional_pct >= regional_threshold:
            kept.append((t, path, "regional_change"))
            kept_small.append(small)
        # else: dropped as a near-duplicate of something already kept

    return kept


def _thin_to_max(kept: list, max_frames: int) -> list:
    if max_frames is None or len(kept) <= max_frames:
        return kept
    idx = np.linspace(0, len(kept) - 1, max_frames).round().astype(int)
    idx = sorted(set(idx.tolist()))
    return [kept[i] for i in idx]


def make_grids(frames_dir: Path, grids_dir: Path, frame_files: list) -> list:
    grids_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for g, start in enumerate(range(0, len(frame_files), 9)):
        chunk = frame_files[start:start + 9]
        thumbs = [Image.open(p).convert("RGB") for p in chunk]
        w, h = thumbs[0].size
        cols = 3
        rows = (len(thumbs) + cols - 1) // cols
        canvas = Image.new("RGB", (w * cols, h * rows), (20, 20, 20))
        for i, im in enumerate(thumbs):
            im = im.resize((w, h))
            canvas.paste(im, ((i % cols) * w, (i // cols) * h))
        dest = grids_dir / f"grid_{g:03d}.jpg"
        canvas.save(dest, quality=85)
        written.append(str(dest))
    return written


def extract_frames(video_path: str, out_dir: Path, scene_threshold: float, fps_floor: float,
                    max_frames: int, resolution: int, dedup_threshold: float, dedup_window: int,
                    regional_threshold: float, make_grid: bool) -> dict:
    duration = ffprobe_duration(video_path)
    tmp_dir = out_dir / "_candidates"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    log("pass A: scene-change detection...")
    scene_ts = _scene_change_timestamps(video_path, scene_threshold)
    log(f"  {len(scene_ts)} scene-change candidates")

    log("pass B: density floor...")
    floor_ts = _floor_timestamps(duration, fps_floor)
    log(f"  {len(floor_ts)} floor candidates")

    merged = sorted(set(round(t, 2) for t in scene_ts + floor_ts))
    deduped_ts = []
    for t in merged:
        if not deduped_ts or t - deduped_ts[-1] > 0.15:
            deduped_ts.append(t)

    log(f"extracting {len(deduped_ts)} candidate frames...")
    candidates = _extract_at(video_path, deduped_ts, tmp_dir, resolution)

    log("deduping (global + regional channels)...")
    kept = dedup(candidates, dedup_threshold, dedup_window, regional_threshold)
    kept = _thin_to_max(kept, max_frames)

    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    frame_records = []
    frame_files = []
    for i, (t, path, reason) in enumerate(kept):
        dest = frames_dir / f"frame_{i:04d}.jpg"
        path.replace(dest)
        frame_files.append(dest)
        frame_records.append({
            "file": f"frames/{dest.name}",
            "timestamp_sec": round(t, 2),
            "timestamp": fmt_ts(t),
            "selection_reason": reason,
        })

    grids = []
    if make_grid and frame_files:
        grids = make_grids(frames_dir, out_dir / "grids", frame_files)

    for leftover in tmp_dir.glob("*.jpg"):
        leftover.unlink(missing_ok=True)
    tmp_dir.rmdir()

    return {"frames": frame_records, "grids": grids, "duration_sec": duration}
