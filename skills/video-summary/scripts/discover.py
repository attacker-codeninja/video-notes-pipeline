#!/usr/bin/env python3
"""
discover.py  —  find the Layer 1 data and list the video(s) inside it.

A video-perceive "_layer1" folder may hold ONE video's data (transcript.json etc.
sitting directly inside) or MANY (each video in its own subfolder). This finds
either, and returns the list of per-video data-dirs in order, so the skill can
process them one by one.

Auto-detection when no folder is given: searches the current working directory.

Usage: python3 discover.py [root]     (root defaults to ".")
Prints one JSON object: {"root","mode":"single|multi|none","videos":[...]}
"""
import sys, os, json, re

def parse_ts(s):
    if not s: return None
    try: p=[float(x) for x in s.strip().split(":")]
    except ValueError: return None
    return {3:p[0]*3600+p[1]*60+p[2] if len(p)==3 else 0,
            2:p[0]*60+p[1] if len(p)==2 else 0,
            1:p[0] if len(p)==1 else 0}.get(len(p))

def duration_of(d):
    mf=os.path.join(d,"MANIFEST.txt")
    if os.path.exists(mf):
        m=re.search(r"^duration:\s*(.+)$",open(mf,encoding="utf-8",errors="replace").read(),re.M)
        if m: return m.group(1).strip()
    return None

def title_guess_of(d):
    tj=os.path.join(d,"transcript.json")
    try: segs=json.load(open(tj,encoding="utf-8"))
    except Exception: return None
    cands=[]
    for s in segs:
        if (s.get("start") or 0)<150:
            oh=s.get("frame_ocr_hint") or {}
            for line in (oh.get("ocr_text") or "").splitlines():
                line=line.strip()
                if len(re.findall(r"[A-Za-z][A-Za-z0-9'+]{1,}",line))>=4 and len(line)<=90:
                    cands.append(line)
    if not cands: return None
    cands.sort(key=lambda x:(-len(re.findall(r"[A-Za-z]+",x)),len(x)))
    return cands[0]

def find_video_dirs(root, max_depth=3):
    """Every dir (root or nested, up to max_depth) that has transcript.json is one video."""
    hits=[]
    root=os.path.abspath(root)
    base_depth=root.rstrip(os.sep).count(os.sep)
    for cur,dirs,files in os.walk(root):
        if cur.rstrip(os.sep).count(os.sep)-base_depth>max_depth:
            dirs[:]=[]; continue
        dirs[:]=[x for x in dirs if x not in ("_layer2","__pycache__")]  # skip our work dirs
        if "transcript.json" in files:
            hits.append(cur); dirs[:]=[]   # don't descend into a video dir
    return sorted(hits)

def resolve_root(arg):
    """arg may be None. Try: given path -> ./_layer1 -> ./layer1 -> cwd itself."""
    if arg:
        return arg
    for c in ("_layer1","layer1"):
        if os.path.isdir(c) and find_video_dirs(c): return c
    return "."

def main():
    arg = sys.argv[1] if len(sys.argv)>1 else None
    root = resolve_root(arg)
    vids = find_video_dirs(root)
    if not vids:
        print(json.dumps({"root":os.path.abspath(root),"mode":"none","videos":[]}))
        return
    single = (len(vids)==1 and os.path.abspath(vids[0])==os.path.abspath(root))
    out={"root":os.path.abspath(root),
         "mode":"single" if single else "multi",
         "videos":[{"index":i,"dir":d,"name":os.path.basename(d.rstrip(os.sep)) or os.path.basename(os.path.dirname(d)),
                    "duration_str":duration_of(d),"title_guess":title_guess_of(d)}
                   for i,d in enumerate(vids)]}
    print(json.dumps(out,ensure_ascii=False,indent=1))

if __name__=="__main__":
    main()
