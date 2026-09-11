#!/usr/bin/env python3
"""
state.py  —  the rolling Canonical Knowledge store (canonical.json) + progress.

Canonical Knowledge is the single source of truth. Claude does the SEMANTIC work
(understanding, deciding merges, reconciling); this script does only the
DETERMINISTIC work: structural merge by id, dedup, centrality, priority boost,
focused context-package selection, presentation slicing, freeze gate, resume.

Subcommands:
  init      --evidence E --parts P --work W
  context   --work W --part N              (focused context package for part N -> stdout)
  merge     --work W --delta D             (merge Claude's per-part delta)
  reconcile --work W --file R              (apply Claude's merge/split/resolve ops)
  select    --work W                       (full frozen knowledge for presentation)
  freeze    --work W [--force]
  status    --work W

IDs are stable slugs chosen by Claude (e.g. c_recon, cl_paidbug, pt_heavyload).
To CONTINUE a concept across parts, Claude reuses the id it saw in the context
package. Accidental duplicates are cleaned in the reconcile step.
"""
import sys, os, json, argparse
from collections import defaultdict

PRIO = ["P0", "P1", "P2", "P3"]
STATUS_RANK = {  # never regress a concept's maturity on merge
    "introduced": 0, "developing": 1, "established": 2,
    "refined": 3, "corrected": 4, "uncertain": 1, "disputed": 2,
}
# relationship types that confer importance (used for centrality)
IMPORTANT_EDGES = {"supports", "explains", "depends_on", "illustrates",
                   "answers", "leads_to", "causes", "qualified_by"}

def _p(w, name): return os.path.join(w, name)
def _load(p): return json.load(open(p, encoding="utf-8"))
def _save(p, o): json.dump(o, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ---------------------------------------------------------------- init
def cmd_init(a):
    os.makedirs(a.work, exist_ok=True)
    ev = _load(a.evidence); parts = _load(a.parts)
    m = ev["meta"]
    canonical = {
        "video": {
            "title": m.get("title"), "title_guess": m.get("title_guess"),
            "url": m.get("url"), "author": m.get("author"),
            "duration_str": m.get("duration_str"), "duration_sec": m.get("duration_sec"),
            "language": m.get("language"), "source": m.get("source"),
        },
        "concepts": [], "claims": [], "relationships": [],
        "pending_threads": [], "uncertainty": [], "visual_knowledge": [],
        "coverage": {"parts": []},
        "frozen": False,
    }
    progress = {"n_parts": parts["n_parts"], "holistic": parts.get("holistic", False),
                "parts_done": [], "reconciled": False, "validated": False, "frozen": False}
    _save(_p(a.work, "canonical.json"), canonical)
    _save(_p(a.work, "progress.json"), progress)
    # keep evidence + parts beside the state so context/merge can reach them
    _save(_p(a.work, "evidence.json"), ev)
    _save(_p(a.work, "parts.json"), parts)
    print(f"[state:init] work={a.work}  parts={parts['n_parts']}  (holistic={progress['holistic']})")

# ---------------------------------------------------------------- context
def cmd_context(a):
    ev = _load(_p(a.work, "evidence.json"))
    parts = _load(_p(a.work, "parts.json"))
    can = _load(_p(a.work, "canonical.json"))
    part = parts["parts"][a.part]
    seg_lo, seg_hi = (part["seg_range"] + [None, None])[:2]
    part_segs = [s for s in ev["segments"]
                 if seg_lo is not None and seg_lo <= s["i"] <= seg_hi]
    part_frames = [f for f in ev["frames"]
                   if f["t"] is not None and part["t_start"] <= f["t"] < part["t_end"]]

    # active concepts: everything not archived, richest first (centrality then priority)
    _recompute(can)
    active = sorted(can["concepts"],
                    key=lambda c: (-c.get("_centrality", 0), PRIO.index(c.get("priority_effective", "P3"))))
    active_slim = [{"id": c["id"], "name": c["name"], "type": c.get("type"),
                    "status": c.get("status"), "meaning": c.get("meaning")} for c in active[:25]]
    pend = [pt for pt in can["pending_threads"] if pt.get("status") not in ("resolved",)]

    pkg = {
        "part_index": a.part,
        "part_span": [part["t_start"], part["t_end"]],
        "is_first_part": a.part == 0,
        "global_so_far": can["coverage"]["parts"][-3:],       # recent coverage notes
        "active_concepts": active_slim,                        # reuse these ids to CONTINUE
        "pending_threads": pend,                               # carry forward / resolve
        "frames_dir_present": ev["meta"]["frames_dir_present"],
        "part_evidence": {
            "segments": [{
                "i": s["i"], "start": s["start"], "end": s["end"],
                "text": s["text"], "confidence": s["confidence"],
                "indep_text": s["indep_text"], "indep_match": s["indep_match"],
                "alt_text": s["alt_text"],
                "ocr_supports": s["ocr_supports"], "ocr_text": s["ocr_text"],
                "vad": s["vad"], "flag": s["flag"], "flag_reason": s["flag_reason"],
            } for s in part_segs],
            "frames": [{"file": f["file"], "abs": f["abs"], "t": f["t"],
                        "reason": f["reason"]} for f in part_frames],
        },
    }
    print(json.dumps(pkg, ensure_ascii=False, indent=1))

# ---------------------------------------------------------------- merge
def _upsert(lst, item, key="id"):
    for i, x in enumerate(lst):
        if x.get(key) == item.get(key):
            return i
    return -1

def cmd_merge(a):
    can = _load(_p(a.work, "canonical.json"))
    prog = _load(_p(a.work, "progress.json"))
    d = _load(a.delta)
    part = d.get("part")

    for c in d.get("concepts", []):
        j = _upsert(can["concepts"], c)
        if j < 0:
            c.setdefault("evidence", []); c.setdefault("aliases", [])
            can["concepts"].append(c)
        else:
            cur = can["concepts"][j]
            # extend, never silently regress status
            if c.get("meaning"): cur["meaning"] = c["meaning"]
            if c.get("priority"): cur["priority"] = c["priority"]
            if c.get("status") and STATUS_RANK.get(c["status"], 0) >= STATUS_RANK.get(cur.get("status", "introduced"), 0):
                cur["status"] = c["status"]
            for al in c.get("aliases", []):
                if al not in cur.setdefault("aliases", []): cur["aliases"].append(al)
            cur.setdefault("evidence", []).extend(c.get("evidence", []))

    for cl in d.get("claims", []):
        j = _upsert(can["claims"], cl)
        if j < 0: can["claims"].append(cl)
        else: can["claims"][j].update(cl)

    for r in d.get("relationships", []):
        sig = (r.get("from"), r.get("to"), r.get("type"))
        if sig not in {(x.get("from"), x.get("to"), x.get("type")) for x in can["relationships"]}:
            can["relationships"].append(r)

    for pt in d.get("pending_threads", []):
        j = _upsert(can["pending_threads"], pt)
        if j < 0: can["pending_threads"].append(pt)
        else: can["pending_threads"][j].update(pt)

    for u in d.get("uncertainty", []):
        sig = (u.get("ref"), u.get("why"))
        if sig not in {(x.get("ref"), x.get("why")) for x in can["uncertainty"]}:
            can["uncertainty"].append(u)

    can["visual_knowledge"].extend(d.get("visual_knowledge", []))

    if d.get("coverage_note"):
        can["coverage"]["parts"].append({"part": part, "note": d["coverage_note"]})

    _recompute(can)
    _save(_p(a.work, "canonical.json"), can)
    if part is not None and part not in prog["parts_done"]:
        prog["parts_done"].append(part); prog["parts_done"].sort()
    _save(_p(a.work, "progress.json"), prog)
    print(f"[state:merge] part {part} merged. "
          f"concepts={len(can['concepts'])} claims={len(can['claims'])} "
          f"rels={len(can['relationships'])} pending={len(can['pending_threads'])} "
          f"done={len(prog['parts_done'])}/{prog['n_parts']}")

# ---------------------------------------------------------------- reconcile
def cmd_reconcile(a):
    """Apply Claude's reconciliation ops. Ops:
       {"op":"merge","from":"c_x","into":"c_y"}          (redirect edges+evidence, drop c_x)
       {"op":"split","id":"c_x","into":[{...new nodes}]} (Claude supplies replacements)
       {"op":"set_status","id":"c_x","status":"corrected"}
       {"op":"set_priority","id":"c_x","priority":"P0"}
       {"op":"resolve_thread","id":"pt_x","status":"resolved","note":"..."}
       {"op":"add_relationship","from":..,"to":..,"type":"corrected_by"}
    """
    can = _load(_p(a.work, "canonical.json"))
    prog = _load(_p(a.work, "progress.json"))
    ops = _load(a.file)
    idx = {c["id"]: c for c in can["concepts"]}
    for op in ops.get("ops", []):
        k = op.get("op")
        if k == "merge":
            src, dst = op["from"], op["into"]
            if src in idx and dst in idx:
                idx[dst].setdefault("evidence", []).extend(idx[src].get("evidence", []))
                for al in [src] + idx[src].get("aliases", []):
                    if al not in idx[dst].setdefault("aliases", []): idx[dst]["aliases"].append(al)
                for r in can["relationships"]:
                    if r.get("from") == src: r["from"] = dst
                    if r.get("to") == src: r["to"] = dst
                can["concepts"] = [c for c in can["concepts"] if c["id"] != src]
                idx = {c["id"]: c for c in can["concepts"]}
        elif k == "split":
            can["concepts"] = [c for c in can["concepts"] if c["id"] != op["id"]]
            can["concepts"].extend(op["into"])
            idx = {c["id"]: c for c in can["concepts"]}
        elif k == "set_status" and op["id"] in idx:
            idx[op["id"]]["status"] = op["status"]
        elif k == "set_priority" and op["id"] in idx:
            idx[op["id"]]["priority"] = op["priority"]
        elif k == "resolve_thread":
            for pt in can["pending_threads"]:
                if pt.get("id") == op["id"]:
                    pt["status"] = op.get("status", "resolved")
                    if op.get("note"): pt["resolution"] = op["note"]
        elif k == "add_relationship":
            sig = (op.get("from"), op.get("to"), op.get("type"))
            if sig not in {(x.get("from"), x.get("to"), x.get("type")) for x in can["relationships"]}:
                can["relationships"].append({"from": op["from"], "to": op["to"], "type": op["type"]})
    _recompute(can)
    _save(_p(a.work, "canonical.json"), can)
    prog["reconciled"] = True
    _save(_p(a.work, "progress.json"), prog)
    print(f"[state:reconcile] applied {len(ops.get('ops', []))} op(s). concepts now {len(can['concepts'])}")

# ---------------------------------------------------------------- select (presentation)
def cmd_select(a):
    # One output only: the complete frozen knowledge. No modes, no priority
    # filtering. Depth of the written note follows the video's own density;
    # priority_effective still travels with each node so the writer knows what
    # is load-bearing vs supporting.
    can = _load(_p(a.work, "canonical.json"))
    _recompute(can)
    out = {
        "video": can["video"],
        "concepts": can["concepts"],
        "claims": can["claims"],
        "relationships": can["relationships"],
        "pending_threads": can["pending_threads"],
        "uncertainty": can["uncertainty"],
        "visual_knowledge": can["visual_knowledge"],
        "coverage": can["coverage"],
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))

# ---------------------------------------------------------------- freeze / status
def cmd_freeze(a):
    prog = _load(_p(a.work, "progress.json"))
    can = _load(_p(a.work, "canonical.json"))
    missing = [i for i in range(prog["n_parts"]) if i not in prog["parts_done"]]
    if missing and not a.force:
        print(f"[state:freeze] REFUSED — parts not processed: {missing}. "
              f"Process them or pass --force.", file=sys.stderr); sys.exit(1)
    prog["frozen"] = True; can["frozen"] = True
    _save(_p(a.work, "progress.json"), prog); _save(_p(a.work, "canonical.json"), can)
    unresolved = [pt["id"] for pt in can["pending_threads"] if pt.get("status") != "resolved"]
    print(f"[state:freeze] FROZEN. concepts={len(can['concepts'])} claims={len(can['claims'])} "
          f"unresolved_threads={len(unresolved)} (kept as pending, not invented).")

def cmd_status(a):
    prog = _load(_p(a.work, "progress.json"))
    can = _load(_p(a.work, "canonical.json"))
    done = prog["parts_done"]; miss = [i for i in range(prog["n_parts"]) if i not in done]
    print(json.dumps({
        "parts_done": done, "parts_remaining": miss,
        "reconciled": prog["reconciled"], "validated": prog["validated"],
        "frozen": prog["frozen"],
        "counts": {"concepts": len(can["concepts"]), "claims": len(can["claims"]),
                   "relationships": len(can["relationships"]),
                   "pending_threads": len(can["pending_threads"]),
                   "uncertainty": len(can["uncertainty"]),
                   "visual_knowledge": len(can["visual_knowledge"])},
    }, ensure_ascii=False, indent=1))

# ---------------------------------------------------------------- shared: centrality + priority
def _recompute(can):
    indeg = defaultdict(int)
    for r in can["relationships"]:
        if r.get("type") in IMPORTANT_EDGES and r.get("to"):
            indeg[r["to"]] += 1
    for c in can["concepts"]:
        cen = indeg.get(c["id"], 0)
        c["_centrality"] = cen
        base = c.get("priority", "P2")
        if base not in PRIO: base = "P2"
        eff = PRIO.index(base)
        if cen >= 2 and eff > 0:      # high-centrality node -> one tier up
            eff -= 1
        c["priority_effective"] = PRIO[eff]
    for cl in can["claims"]:
        cl.setdefault("priority_effective", cl.get("priority", "P1"))

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init");      p.add_argument("--evidence", required=True); p.add_argument("--parts", required=True); p.add_argument("--work", required=True); p.set_defaults(fn=cmd_init)
    p = sub.add_parser("context");   p.add_argument("--work", required=True); p.add_argument("--part", type=int, required=True); p.set_defaults(fn=cmd_context)
    p = sub.add_parser("merge");     p.add_argument("--work", required=True); p.add_argument("--delta", required=True); p.set_defaults(fn=cmd_merge)
    p = sub.add_parser("reconcile"); p.add_argument("--work", required=True); p.add_argument("--file", required=True); p.set_defaults(fn=cmd_reconcile)
    p = sub.add_parser("select");    p.add_argument("--work", required=True); p.add_argument("--mode", required=False, help=argparse.SUPPRESS); p.set_defaults(fn=cmd_select)
    p = sub.add_parser("freeze");    p.add_argument("--work", required=True); p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_freeze)
    p = sub.add_parser("status");    p.add_argument("--work", required=True); p.set_defaults(fn=cmd_status)
    a = ap.parse_args(); a.fn(a)

if __name__ == "__main__":
    main()
