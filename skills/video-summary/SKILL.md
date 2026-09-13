---
name: video-summary
description: Deeply understand a video from its already-produced video-perceive (Layer 1) output folder, build a reconciled Canonical Knowledge representation of it, then write it up once — as a self-learner's own study notes in clear English, with headings and structure taken from the video itself. The note opens with a quick-orientation callout and a complete bulleted Summary right after the metadata, then the full detailed write-up, then a fixed closing Ending Deep-Dive Layer (a top-student's-own-words deep dive, Interview Q&A, conditional Code Walkthrough/Mind Map/Formulas, and a final Quick Revision callout). One output, no modes: the full meaningful knowledge of the video, always. This is NOT a transcript shortener: it understands the video first, freezes that understanding, then writes from it. Consumes Layer 1 evidence (transcript.json, frames.json, MANIFEST.txt, frames/); never re-downloads or re-transcribes. Auto-detects the _layer1 folder in the current directory when no path is given, and handles a folder holding one video or many (processed one by one). Use when the user points at (or is inside) a _layer1 folder and wants a summary / notes / overview.
argument-hint: "[folder] [terminal|md|html]"
allowed-tools: Bash, Read, Write, AskUserQuestion
user-invocable: true
---

# /video-summary

Turn a **video-perceive (Layer 1) output folder** into a faithful understanding of the
video, written up once as a self-learner's own study notes — in **clear English, always**.

**One output, no modes.** Not "quick vs detailed vs complete" — always the complete
meaningful knowledge of the video: everything worth learning from it, and a clear picture
of what the video actually said. The note's length follows the video's own density, not a
setting.

The one rule this skill must never break:

> **First understand the video completely. Freeze that understanding. Then write it up
> in full — every meaningful piece of knowledge — as the learner's own notes. Never
> sacrifice correctness or meaningful knowledge to make the output shorter.**

The hard separation the whole design rests on:

```
Layer 1 evidence  →  Layer 2 understanding  →  Canonical Knowledge  →  FREEZE  →  presentation
   (given)              (you, per part)          (state.py)                        (you, English)
```

Layer 1 already did perception (download, audio, transcript, frames, OCR, VAD). **Do not
rebuild any of it.** You consume its folder. Deterministic work (discovery, parsing,
segmenting, state-merge, centrality, selection, rendering, resume) is done by the bundled
scripts; the semantic work (understanding, reconciling, validating, presenting) is done by
you, using `reference/rubrics.md` as the judgment rules.

`${SKILL_DIR}` below = this skill's directory.

---

## Step 0 — read the arguments

Arguments are **bare positional words, any order, all optional** — no `--` flags, **no
mode word** (there are no modes):

- a **format** word: `terminal` | `md` | `html`  (default **terminal**)
- a **folder** path (anything that isn't a format word)

Classify:
- `FORMAT` = the first token equal to terminal/md/html (else `terminal`)
- `FOLDER` = the first token that is neither (else empty → auto-detect in Step 1)

A bare `/video-summary` is valid — just run (terminal format, auto-detect folder). Do not
show a help block, do not ask a follow-up.

```
video-summary — understands a video-perceive (_layer1) folder and writes English study notes

USAGE
  /video-summary [folder] [format]

One output: the video's complete meaningful knowledge, written as a self-learner's own
notes — a quick-summary callout and a complete bulleted summary right after the metadata,
then the full detailed write-up, shaped by the video itself.

FORMAT  (optional — default: terminal)
  terminal   writes straight into the chat (no file)
  md         produces a .md file
  html       produces a .html file (Mermaid diagrams render)

FOLDER  (optional — default: auto-detects _layer1 in the current directory)
  - a _layer1 holding one video or many — each is processed in turn

EXAMPLES
  /video-summary
  /video-summary md
  /video-summary ./_layer1 html
```

## Step 1 — find the Layer 1 data and list the video(s)

Auto-detect the folder (uses `FOLDER` if given, else searches the current directory) and
enumerate the video(s) inside it:

```bash
python3 "${SKILL_DIR}/scripts/discover.py" "${FOLDER:-}"
```

This prints `{"root","mode":"single|multi|none","videos":[{index,dir,name,duration_str,title_guess}]}`.

- `mode: none` → no video-perceive data found. Stop and tell the user to `cd` into the
  folder that has `_layer1`, or pass the folder as an argument. **Do not** try to perceive
  a video yourself.
- `mode: single` → one video (data sits directly in the folder). One job.
- `mode: multi` → several videos, each in its own subfolder. You will process them **one
  by one, in listed order**. If there are **more than 3**, first show the user the count
  and the `title_guess`/`name` of each, and confirm they want the whole batch (it costs
  real time and tokens). For 1–3, just proceed.

## Step 2 — read the rules once (applies to every video)

`Read` `${SKILL_DIR}/reference/rubrics.md` and `${SKILL_DIR}/reference/canonical_schema.md`
before processing anything. They define "meaningful", triangulation, priority, merge/split,
uncertainty vs pending, and the exact delta JSON shape. Follow them literally.

---

## Per-video pipeline — run Steps A–F for EACH video's `dir`, in order

Process one video completely before starting the next, so an interruption leaves finished
videos intact.

**Never nest your working dir or the final note inside a folder literally named `_layer1`
— that folder is Layer 1's own output and stays exactly as `video-perceive` left it.**
Work out `WORK` (your scratch dir) and `NOTE_DIR`/`NOTE_STEM` (where the final note goes,
and its filename stem) from each video's `dir` like this:

```
if dir's own folder name == "_layer1":       # single-video perceive_single.py run: <date>_<title-slug>/_layer1/
    NOTE_DIR  = dir.parent                   # the <date>_<title-slug> folder itself
    NOTE_STEM = dir.parent's folder name      # "<date>_<title-slug>"
else:                                         # multi-video / channel run: dir is already
    NOTE_DIR  = dir                          #   that video's own root, e.g. _layer1/NNN-Title/
    NOTE_STEM = dir's own folder name         #   (nesting inside it is fine — it isn't "_layer1")
WORK = NOTE_DIR / "layer2-temp"
```

So for a single `perceive_single.py`-produced video you get:
```
<date>_<title-slug>/
  _layer1/            <- untouched Layer 1 output
  layer2-temp/        <- WORK: evidence.json, parts.json, canonical.json, deltas, progress.json
  <date>_<title-slug>.md   <- the final note (NOTE_DIR/NOTE_STEM.md)
```
`layer2-temp/` holds the frozen understanding and makes a second FORMAT cheap (Step B's
resume note) — **don't delete it as part of normal completion.** Only delete it when the
user explicitly asks to clean up; the delivered `.md`/`.html` file is what matters long-term.

### Step A — normalize the evidence
```bash
python3 "${SKILL_DIR}/scripts/parse_perceive.py" "<dir>" "$WORK/evidence.json"
```
Prints duration, language, segment/frame counts, how many segments are **flagged** (spoken
reading suspect — needs a frame check), and a **title guess**. Everything downstream reads
`evidence.json`, never the raw files.

### Step B — segment into candidate knowledge parts + init state
```bash
python3 "${SKILL_DIR}/scripts/segment.py" "$WORK/evidence.json" "$WORK/parts.json"
python3 "${SKILL_DIR}/scripts/state.py" init --evidence "$WORK/evidence.json" --parts "$WORK/parts.json" --work "$WORK"
```
Parts are processing units on natural signals (scene changes, silence gaps), not clock
intervals; a short video collapses to one holistic part. Finer sub-topics inside a part are
captured as concept nodes with their own timestamps, not as new parts.

**Resume:** if `$WORK/progress.json` already shows parts done, skip those in Step C
(`state.py status --work "$WORK"` shows what's left). A re-run continues, it doesn't restart.
(If the video is already frozen — e.g. the user just wants it in a different FORMAT — skip
straight to Step F and reuse the frozen knowledge; do not re-understand.)

### Step C — per-part understanding loop (the core; one part at a time, in order)
For each part index `N` not already done:

1. **Focused context package** (bounded — not the whole history):
   ```bash
   python3 "${SKILL_DIR}/scripts/state.py" context --work "$WORK" --part N
   ```
   Gives the part's segments (with all Layer 1 triangulation signals), the part's frames
   (absolute paths), the active concepts (**reuse their ids to continue a concept**), and
   open pending threads.

2. **Understand — triangulate, don't transcribe** (`rubrics.md §2`): trust content where
   source A (`text`) and source B (`indep_text`) agree; for any `flag: true` segment
   carrying a concrete claim (number, name, command, URL, term), `Read` the frame(s) at
   that timestamp (`part_evidence.frames[].abs`) and let on-screen text decide. If nothing
   resolves it, record `uncertainty` — don't guess. Read frames selectively (boundaries,
   flagged claims, slides/code), not all of them. Extract only **meaningful** knowledge
   (`rubrics.md §1`): concepts, claims (with type + source — opinion stays opinion),
   evidence refs, relationships, examples, processes, pending threads, uncertainty, visual
   knowledge. Write English `meaning`/`statement`; set first-pass `priority` (`§3`).

3. **Emit the delta and merge:**
   ```bash
   # write $WORK/delta_N.json per canonical_schema.md
   python3 "${SKILL_DIR}/scripts/state.py" merge --work "$WORK" --delta "$WORK/delta_N.json"
   ```
   **Never hand-edit `canonical.json`.**

### Step D — reconcile (once, after all parts)
`Read` the full list (`state.py select --work "$WORK"`), then apply
`rubrics.md §4–6`: merge accidental duplicate concepts (same meaning+evidence — **never on
name alone**); split a node that's really two; resolve contradictions to a final **scoped**
position (keep history via `corrected_by`/`qualified_by`, don't erase the earlier claim);
mark threads `resolved` or `unresolved_at_end` (**invent no answers**).
```bash
# write $WORK/reconcile.json (see canonical_schema.md "Reconcile ops")
python3 "${SKILL_DIR}/scripts/state.py" reconcile --work "$WORK" --file "$WORK/reconcile.json"
```

### Step E — coverage + validation, then FREEZE
Check every P0 concept, major argument, examples, conclusions, creator intent, and
important corrections/contradictions are represented; if a real gap exists, targeted re-read
of that part's evidence/frames and merge a fixing delta — don't reprocess everything. Then:
```bash
python3 "${SKILL_DIR}/scripts/state.py" freeze --work "$WORK"
```
Freeze refuses if any part is unprocessed. After freeze, **Canonical Knowledge is the source
of truth** — presentation reads from it and must not re-interpret the video.

### Step F — write the notes (one output, in English)
1. Get the full frozen knowledge:
   ```bash
   python3 "${SKILL_DIR}/scripts/state.py" select --work "$WORK"
   ```
   This returns **everything** — all concepts, claims, relationships, uncertainty,
   pending threads, visual knowledge. `priority_effective` still rides on each node so
   you know what is load-bearing vs supporting, but nothing is filtered out. The note
   covers **all meaningful knowledge**; its length follows the video's density.
2. `Read` `${SKILL_DIR}/reference/templates.md` and write the note **in clear English**
   as the **self-learner ROLE** described there, following its 5-stage **METHOD**
   (Grasp → Spine → Layout → Write → Honesty-check). There is **no fixed skeleton and no
   mode**: structure, heading names, order and formatting come from *this video's* own
   knowledge and type, re-decided per video — two videos should not come out the same
   shape. Honour the FIXED minimums from that file: **YAML frontmatter** + a metadata
   block at the top (`N/A (not present in Layer 1 output)` for any null `url`/`author`;
   confirm `title` from the title-card frame if null; never fabricate); present only
   what's in the frozen knowledge (**invent nothing**); opinions stay opinions ("the
   creator argues…", "in the creator's view…"); scopes, qualifications, unresolved
   threads stay visible; don't silently resolve contradictions; **uncertainty woven
   inline in the learner's own words**, no dedicated heading needed; plain, clear
   English — explain any jargon the first time it appears. No filler, no transcript
   dumping. Format the note per the `obsidian-md-formatter` skill's conventions (load it
   via the Skill tool) — callouts for warnings/tips/definitions, tables for comparisons,
   footnotes for external sources, wiki-links only for genuine cross-references (usually
   none here, don't force it) — so the file drops into a vault with zero reformatting.
   Use a **Mermaid** diagram only where structure is genuinely visual, built strictly
   from Canonical Knowledge.
   **Right after the metadata block, before any of the video's own sections, place
   two fixed things in this order:**
   - a `> [!abstract] Quick Summary` callout — 2-4 plain-prose lines giving instant
     orientation (what the video is, what it covers);
   - a `## Summary` section — the complete bulleted list covering every
     meaningful point in the note, one blank line between consecutive bullets.

   Only after both does the video's own detailed write-up begin (same full depth as
   always, just positioned below instead of at the end). **After that write-up, a
   fixed Ending Deep-Dive Layer always closes the note** (full spec in
   `reference/templates.md`, FIXED §7): `## What I Actually Learned` (your own
   top-student-voice synthesis, not a reworded summary), `## Interview Q&A`
   (topic-grouped `[!question]` callouts with full answers), `## Code Walkthrough` /
   `## Mind Map` / `## Formulas` (each only when the video actually earns it —
   skip cleanly otherwise), and `## Quick Revision` last (one terse
   `[!abstract]` callout, always present).
   Save to `NOTE_DIR/NOTE_STEM.md` (e.g. `2026-08-26_why-hes-hunted-for-a-year-without-
   finding-a-valid-bug.md`) — **not** into `WORK`, and never inside `_layer1`.
3. **Validate** against the `select` output (`rubrics.md §8`): coverage (every meaningful
   node represented, and the Summary near the top misses nothing), accuracy
   (every concrete claim maps to a node, nothing invented), faithfulness (opinions stay
   opinions, scopes intact), uncertainty preserved, clear and correct English throughout,
   and the Ending Deep-Dive Layer present and correctly ordered (conditional pieces
   skipped only when genuinely not earned). Fix any failing section and re-check.
4. Deliver in the chosen format:
   - `terminal` (default): **do not call any script.** Put the note you just wrote
     (`NOTE_DIR/NOTE_STEM.md`) straight into your chat reply, YAML frontmatter and all. A
     ` ```mermaid ` block stays as-is — the chat renders it.
   - `md`: the file at `NOTE_DIR/NOTE_STEM.md` already **is** the deliverable — just tell
     the user its path.
   - `html`: additionally render it (frontmatter, callouts and Mermaid all render):
     ```bash
     python3 "${SKILL_DIR}/scripts/render.py" --in "NOTE_DIR/NOTE_STEM.md" --format html --out "NOTE_DIR/NOTE_STEM.html"
     ```
     (dark theme + Mermaid via CDN, opens in a browser.) `render.py` is only for `html` —
     the `md` deliverable needs no rendering pass, and terminal never touches it.

**Multi-video:** in `terminal` mode, write each video's notes in turn (a clear heading per
video, `title_guess`/`name`). In `md`/`html` mode, each video gets its own `NOTE_DIR` and
`NOTE_STEM` per the rule above — list all the resulting paths at the end.

---

## Non-negotiables (what this skill must never become)
- **Not a transcript shortener**, **not a keyword extractor**, **not a generic "summarize
  this video" prompt** — one frozen understanding, written up once in full.
- **No modes, no depth dial.** Always the complete meaningful knowledge. The note's
  length comes from the video, never from a setting.
- **Not a fixed-template filler.** No section skeleton for the *body*. The note is shaped
  like a real self-learner's own notes — structure and heading names in the body come from
  the video, re-decided each run. Fixed regardless of video: YAML frontmatter, the metadata
  block, English prose, faithfulness, the Quick Summary callout + `## Summary`
  placed right after the metadata, and the six-part Ending Deep-Dive Layer
  (`## What I Actually Learned` → `## Interview Q&A` → conditional
  `## Code Walkthrough`/`## Mind Map`/`## Formulas` → `## Quick Revision`) that always
  closes the note — see `reference/templates.md` FIXED §7 for the full spec.
- **Clear, plain English** — whatever language the video is in, the notes are written in
  English throughout; any term the learner wouldn't already know gets explained inline on
  first use.
- **Never fabricate** — no invented facts, guessed transcript words, made-up URL/author,
  invented answers to unresolved questions, or invented visual facts.
- **Format never changes the underlying knowledge** — presentation preferences never
  contaminate Canonical Knowledge.
- **Don't re-perceive** — Layer 1's folder is the input; download/whisper/frames are not
  this skill's job.

## Notes
- Long videos: length changes strategy (more parts), never the completeness standard. Keep
  every P0 through compression; archived ≠ deleted.
- Frame reading is selective and purpose-driven (boundaries, flagged concrete claims,
  slides/code) — as many as accuracy needs, not a fixed sample.
- All intermediates live under each video's `layer2-temp` (sibling to `_layer1`, never
  inside it) so runs are resumable and re-rendering in another FORMAT is cheap.
