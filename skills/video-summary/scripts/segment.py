#!/usr/bin/env python3
"""
segment.py  —  propose CANDIDATE knowledge-part boundaries from evidence.json

These are processing units, not final knowledge boundaries. The rule
(from the architecture) is: minimum necessary decomposition, boundaries on
natural signals not on the clock. This script gives Layer 2 a small, sane set
of coarse parts to iterate over; Claude captures finer sub-topic structure
inside each part as concept nodes with their own timestamps.

Signals used (all already in Layer 1, no model needed):
  - frame selection_reason == 'global_change'  (a real visual scene shift)
  - large silence gaps between consecutive speech segments (a likely cut)
A scene change or a gap ALONE is not forced to be a boundary — candidates are
snapped together and a minimum part length is enforced so we don't fragment.

Short/dense videos collapse to a single holistic part on purpose.

Usage: python3 segment.py <evidence.json> <out_parts.json>
"""
import sys, json, math

def main():
    if len(sys.argv) != 3:
        print("usage: segment.py <evidence.json> <out_parts.json>", file=sys.stderr); sys.exit(2)
    ev = json.load(open(sys.argv[1], encoding="utf-8"))
    segs = ev["segments"]; frames = ev["frames"]
    dur = ev["meta"]["duration_sec"] or (segs[-1]["end"] if segs else 0)

    # ---- holistic case: short video -> one part ----
    if dur <= 300 or len(segs) <= 40:
        parts = [_mk_part(0, 0.0, dur, segs, frames)]
        _write(parts, dur, sys.argv[2], holistic=True); return

    # ---- target number of parts (~5 min each), clamped ----
    target = max(1, min(12, round(dur / 300.0)))
    min_part = max(90.0, dur / 12.0)
    step = dur / target

    # ---- collect candidate boundary timestamps ----
    cands = set()
    for f in frames:
        if f["reason"] == "global_change" and f["t"]:
            cands.add(round(f["t"], 2))
    for a, b in zip(segs, segs[1:]):
        if a["end"] and b["start"] and (b["start"] - a["end"]) > 2.5:
            cands.add(round(b["start"], 2))
    cands = sorted(cands)

    # ---- walk time; open a new part when we've covered ~step AND a candidate
    #      boundary is nearby; snap the cut to that candidate ----
    boundaries = [0.0]
    next_target = step
    for t in cands:
        if t >= next_target and (t - boundaries[-1]) >= min_part and (dur - t) >= min_part:
            boundaries.append(t)
            next_target = t + step
    boundaries.append(dur)
    # de-dup / enforce min length one more time
    clean = [boundaries[0]]
    for t in boundaries[1:]:
        if t - clean[-1] >= min_part or t == dur:
            clean.append(t)
    if clean[-1] != dur: clean[-1] = dur

    parts = []
    for idx, (t0, t1) in enumerate(zip(clean, clean[1:])):
        parts.append(_mk_part(idx, t0, t1, segs, frames))
    _write(parts, dur, sys.argv[2], holistic=False)

def _mk_part(idx, t0, t1, segs, frames):
    seg_idx = [s["i"] for s in segs if s["start"] is not None and t0 <= s["start"] < t1]
    if not seg_idx and segs:  # last part safety
        seg_idx = [s["i"] for s in segs if s["start"] is not None and s["start"] >= t0]
    fr_idx  = [f["i"] for f in frames if f["t"] is not None and t0 <= f["t"] < t1]
    # a few representative frames across the part (for cheap orientation)
    key = []
    if fr_idx:
        picks = sorted(set([fr_idx[0], fr_idx[len(fr_idx)//2], fr_idx[-1]]))
        key = [frames[i]["file"] for i in picks]
    return {
        "index": idx,
        "t_start": round(t0, 2), "t_end": round(t1, 2),
        "seg_range": [seg_idx[0], seg_idx[-1]] if seg_idx else [],
        "n_segs": len(seg_idx),
        "frame_range": [fr_idx[0], fr_idx[-1]] if fr_idx else [],
        "n_frames": len(fr_idx),
        "key_frames": key,
    }

def _write(parts, dur, path, holistic):
    obj = {"n_parts": len(parts), "duration_sec": dur, "holistic": holistic, "parts": parts}
    json.dump(obj, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[segment] duration={dur}s -> {len(parts)} part(s){' (holistic)' if holistic else ''}")
    for p in parts:
        print(f"  part {p['index']}: {p['t_start']:>7.1f}-{p['t_end']:<7.1f}s  segs={p['n_segs']:<3} frames={p['n_frames']}")
    print(f"  -> wrote {path}")

if __name__ == "__main__":
    main()
