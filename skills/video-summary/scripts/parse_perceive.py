#!/usr/bin/env python3
"""
parse_perceive.py  —  Layer 1 (video-perceive) output  ->  normalized evidence.json

This is the ONLY place that knows video-perceive's on-disk format. Everything
downstream reads evidence.json, never the raw Layer 1 files. If video-perceive's
format changes, only this adapter changes.

Input : a Layer 1 output folder (the "_layer1" dir) containing at minimum
        transcript.json and frames.json. Optional: MANIFEST.txt,
        native_auto_captions.vtt, frames/ image dir, source.mp4, audio.*
Output: evidence.json  (normalized, with per-segment triangulation signals
        already resolved into flat fields, and absolute frame paths so Layer 2
        can Read the frame images directly).

Usage : python3 parse_perceive.py <layer1_dir> <out_evidence.json>
"""
import sys, os, json, re

def load_json(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def parse_ts(s):
    """'16:05.67' or '01:02:03.4' -> seconds (float)."""
    if s is None: return None
    s = s.strip()
    parts = s.split(":")
    try:
        parts = [float(x) for x in parts]
    except ValueError:
        return None
    if len(parts) == 3:  return parts[0]*3600 + parts[1]*60 + parts[2]
    if len(parts) == 2:  return parts[0]*60 + parts[1]
    if len(parts) == 1:  return parts[0]
    return None

def parse_manifest(path):
    """Pull the few authoritative facts video-perceive writes in plain text."""
    out = {"source": None, "duration_sec": None, "duration_str": None,
           "transcript_source": None}
    if not os.path.exists(path): return out
    txt = open(path, "r", encoding="utf-8", errors="replace").read()
    m = re.search(r"^source:\s*(.+)$", txt, re.M)
    if m: out["source"] = m.group(1).strip()
    m = re.search(r"^duration:\s*(.+)$", txt, re.M)
    if m:
        out["duration_str"] = m.group(1).strip()
        out["duration_sec"] = parse_ts(m.group(1).strip())
    m = re.search(r"segment\(s\)\s+from\s+source:\s*(\w+)", txt)
    if m: out["transcript_source"] = m.group(1).strip()
    return out

def flag_segment(seg):
    """Decide whether a segment's SPOKEN reading is suspect and needs a frame
    check before any concrete claim from it is trusted. Positive OCR support is
    NOT a flag; it's recorded separately as corroboration."""
    reasons = []
    ic = seg.get("independent_check") or {}
    match = (ic.get("match") or "")
    if "disagree" in match: reasons.append("indep_disagree")
    ac = (seg.get("audio_check") or "")
    mcov = re.search(r"coverage=(\d+)%", ac)
    if "no_speech" in ac or (mcov and int(mcov.group(1)) == 0):
        reasons.append("vad_no_speech")
    elif mcov and int(mcov.group(1)) < 40:
        reasons.append("vad_low")
    return reasons

def normalize_segments(raw):
    segs = []
    for i, s in enumerate(raw):
        ic  = s.get("independent_check") or {}
        oh  = s.get("frame_ocr_hint") or {}
        reasons = flag_segment(s)
        segs.append({
            "i": i,
            "start": s.get("start"),
            "end": s.get("end"),
            "text": (s.get("text") or "").strip(),          # source A (primary)
            "source": s.get("source"),
            "confidence": s.get("confidence"),
            "alt_text": s.get("alt_text"),                   # overruled small-model reading
            "indep_text": (ic.get("text") or None),          # source B (independent Whisper)
            "indep_match": (ic.get("match") or None),
            "ocr_supports": (oh.get("supports") or None),    # source C corroboration verdict
            "ocr_text": (oh.get("ocr_text") or None),
            "ocr_frame": (oh.get("frame") or None),
            "ocr_shared_word": (oh.get("shared_word") or None),
            "vad": s.get("audio_check"),
            "language": s.get("language"),
            "translation": s.get("translation"),
            "flag": bool(reasons),                           # spoken reading suspect?
            "flag_reason": reasons,
        })
    return segs

def normalize_frames(raw, layer1_dir):
    frames_abs_ok = os.path.isdir(os.path.join(layer1_dir, "frames"))
    out = []
    for i, f in enumerate(raw):
        rel = f.get("file")
        ab  = os.path.abspath(os.path.join(layer1_dir, rel)) if rel else None
        out.append({
            "i": i,
            "file": rel,
            "abs": ab,
            "exists": bool(ab and os.path.exists(ab)),
            "t": f.get("timestamp_sec"),
            "t_str": f.get("timestamp"),
            "reason": f.get("selection_reason"),
        })
    return out, frames_abs_ok

def guess_title(segs, frames):
    """Best-effort title from early on-screen OCR. A GUESS — Layer 2 confirms
    from the actual frame. Never treated as authoritative."""
    cands = []
    for s in segs:
        if s["ocr_text"] and (s["start"] or 0) < 150:
            for line in s["ocr_text"].splitlines():
                line = line.strip()
                words = re.findall(r"[A-Za-z][A-Za-z0-9'+]{1,}", line)
                if len(words) >= 4 and len(line) <= 90:
                    cands.append(line)
    if not cands: return None
    cands.sort(key=lambda x: (-len(re.findall(r"[A-Za-z]+", x)), len(x)))
    return cands[0]

def main():
    if len(sys.argv) != 3:
        print("usage: parse_perceive.py <layer1_dir> <out_evidence.json>", file=sys.stderr)
        sys.exit(2)
    layer1_dir = os.path.abspath(sys.argv[1])
    out_path   = sys.argv[2]

    # If pointed at a parent, auto-descend into a lone _layer1-style child.
    if not os.path.exists(os.path.join(layer1_dir, "transcript.json")):
        for name in ("_layer1", "layer1"):
            cand = os.path.join(layer1_dir, name)
            if os.path.exists(os.path.join(cand, "transcript.json")):
                layer1_dir = cand; break

    t_path = os.path.join(layer1_dir, "transcript.json")
    f_path = os.path.join(layer1_dir, "frames.json")
    if not os.path.exists(t_path):
        print(f"ERROR: transcript.json not found under {layer1_dir}", file=sys.stderr); sys.exit(1)
    if not os.path.exists(f_path):
        print(f"ERROR: frames.json not found under {layer1_dir}", file=sys.stderr); sys.exit(1)

    man = parse_manifest(os.path.join(layer1_dir, "MANIFEST.txt"))
    raw_segs   = load_json(t_path)
    raw_frames = load_json(f_path)
    segs = normalize_segments(raw_segs)
    frames, frames_ok = normalize_frames(raw_frames, layer1_dir)

    # language = most common per-segment language
    langs = {}
    for s in segs:
        if s["language"]: langs[s["language"]] = langs.get(s["language"], 0) + 1
    language = max(langs, key=langs.get) if langs else None

    dur = man["duration_sec"]
    if not dur:
        cand = [x for x in ([s["end"] for s in segs] + [f["t"] for f in frames]) if x]
        dur = max(cand) if cand else None

    n_flagged = sum(1 for s in segs if s["flag"])
    n_ocr = sum(1 for s in segs if s["ocr_text"])

    evidence = {
        "meta": {
            "layer1_dir": layer1_dir,
            "source": man["source"],
            "duration_sec": dur,
            "duration_str": man["duration_str"] or (f"{int(dur)//60:02d}:{dur%60:05.2f}" if dur else None),
            "language": language,
            "transcript_source": man["transcript_source"],
            "n_segments": len(segs),
            "n_frames": len(frames),
            "frames_dir_present": frames_ok,
            "n_flagged_segments": n_flagged,
            "n_ocr_segments": n_ocr,
            "title_guess": guess_title(segs, frames),
            # These are intentionally null: video-perceive's folder carries no
            # canonical URL/title/author. Layer 2 confirms title from frames and
            # marks url/author "N/A (not in Layer 1 output)" rather than inventing.
            "url": None, "title": None, "author": None,
        },
        "segments": segs,
        "frames": frames,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=1)

    m = evidence["meta"]
    print(f"[parse_perceive] layer1_dir = {layer1_dir}")
    print(f"  duration      : {m['duration_str']} ({m['duration_sec']}s)")
    print(f"  language      : {m['language']}   transcript source: {m['transcript_source']}")
    print(f"  segments      : {m['n_segments']}  (flagged/suspect: {m['n_flagged_segments']})")
    print(f"  frames        : {m['n_frames']}  (image dir present: {m['frames_dir_present']}, with OCR: {m['n_ocr_segments']})")
    print(f"  title guess   : {m['title_guess']!r}  (confirm from frame)")
    print(f"  -> wrote {out_path}")

if __name__ == "__main__":
    main()
