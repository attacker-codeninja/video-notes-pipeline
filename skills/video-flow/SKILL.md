---
name: video-flow
description: End-to-end YouTube video (or playlist/channel) to English study-notes pipeline that touches the local disk as little as possible. Chains video-perceive (Layer 1 perception) and video-summary (Layer 2 understanding) back to back inside a scratch working directory -- a RAM disk on macOS when available (falls back automatically to a plain temp directory everywhere else, or if requested), and delivers only the final .md/.html note flat into the current directory -- everything else (downloaded video, audio, frames, transcript, layer2-temp) is discarded per video. Built for processing many videos over time (a whole channel, in batches, across sessions) without local storage ever growing. Use when the user wants notes from a video/channel and explicitly does not want the raw Layer 1/Layer 2 evidence kept on disk.
argument-hint: "<video-or-channel-url> [--count N|all] [--format md|html] [--out dir] [--order oldest|newest] [--force] [--no-ramdisk]"
allowed-tools: Bash, Read, Skill, AskUserQuestion
user-invocable: true
---

# /video-flow

Turns a YouTube video/playlist/channel URL straight into a saved English study
note, keeping the local disk as clean as possible in between. `/video-perceive`
(download + frames + transcript) and `/video-summary` (understanding +
write-up) both run inside a scratch working directory; only the finished note
file survives, copied flat into the destination directory. The working
directory for that video is deleted immediately after, before the next video
starts -- so local storage never grows no matter how many videos get
processed, today or across many later sessions.

**RAM disk is an optimization, not a requirement.** On macOS, the working
directory is a RAM disk by default (nothing touches the real disk at all while
a video is being processed) -- but this is automatic best-effort: it falls
back transparently to a plain temp directory if RAM disk creation fails for
any reason (not enough free RAM, `diskutil`/`hdiutil` unavailable), and
`--no-ramdisk` skips it outright. On any other OS, a plain temp directory is
used from the start. **Storage safety does not depend on which kind of scratch
space is used** -- the per-video cleanup (delete the working folder right
after its note is delivered) is what actually keeps local storage flat, RAM
disk or not.

**Does not modify `video-perceive` or `video-summary`.** This skill only calls
`video-perceive`'s bundled `perceive_single.py` script directly and invokes
the `video-summary` skill as-is, plus its own small `scripts/flow.py` for
source resolution, working-directory lifecycle, and a processed-video log.
`${SKILL_DIR}` below = this skill's directory; `video-perceive` is expected to
be its sibling (`${SKILL_DIR}/../video-perceive`), which holds for any normal
install where all skills sit side by side under `.claude/skills/`.

## Step 0 -- parse arguments

All optional except the source URL, bare positional/flag words, any order:

- `source` (required): a single video URL, or a playlist/channel URL
- `--count N|all` (default: `1` for a single-video source; **`all` for a
  playlist/channel source** when `--count` isn't given): how many
  **not-yet-processed** videos to do this run. A bare channel/playlist link
  with no `--count` means "process everything still outstanding on this
  channel/playlist, one by one" -- not just one video. `--count` is ignored
  entirely for a single-video source (always exactly that one video).
- `--format md|html` (default `md`): note format. There is no `terminal`
  option here -- the whole point of this skill is a saved file, not chat
  output (use `/video-summary` directly for a terminal read).
- `--out DIR` (default: the current directory, i.e. wherever this skill is
  being run from): where finished notes land, flat -- `<date>_<title-slug>.md`
  directly in this folder, no per-video subfolder. This is also where the
  `.video-flow-processed.log` tracking file lives.
- `--order oldest|newest` (default `oldest`): processing order for a
  playlist/channel source, oldest-upload-first or newest-first.
- `--force`: reprocess videos even if already marked done in the log.
- `--no-ramdisk`: skip the RAM disk even on macOS and always use a plain temp
  directory. Useful on a machine with little free RAM, or simply if the user
  prefers not to use one.

A bare `/video-flow <url>` is valid -- just run with the defaults above.

## Step 1 -- resolve which videos to process

```bash
python3 "${SKILL_DIR}/scripts/flow.py" list "<source>" \
  --order <order> --count <count> --out "<out>" [--force]
```

Prints TAB-separated `id<TAB>title<TAB>url` lines, one per video still to do,
already in the right order, with already-done videos (per the log in `--out`)
already filtered out unless `--force` was given. For a channel/playlist
source with no explicit `--count`, pass `--count all` here so the full
remaining backlog resolves in one go, not just the next video.

If this resolves to **more than 3** videos to process in this run, show the
user the count and titles and confirm before proceeding (mirrors
`/video-summary`'s own batch-confirmation rule) -- this is a real
yt-dlp/whisper/token cost. Once confirmed, proceed through the **entire**
resolved list in Step 3 without stopping or re-asking between videos -- a
channel/playlist run means working through every video in that list before
the task counts as done. If the output is empty, tell the user everything
requested is already processed and stop (no working directory needed).

## Step 2 -- create the scratch working directory (once for the whole run)

```bash
python3 "${SKILL_DIR}/scripts/flow.py" workdir-create [--no-ramdisk] [--size-gb N]
```

Prints `<path>\t<kind>` -- `kind` is `ramdisk` or `plain`. Keep both: `path` is
where processing happens, `kind` is what `workdir-destroy` needs at the end.
Idempotent for the RAM disk case -- reuses an already-mounted one. Pass
`--size-gb` through only if the user explicitly asks for a specific RAM disk
size; otherwise it auto-sizes to a safe fraction of this Mac's RAM.

## Step 3 -- per video, in order

For each `id`, `title`, `url` line from Step 1, process one video completely
(including cleanup) before starting the next -- so an interruption leaves the
working directory clean and every already-finished note intact.

**a. Perceive (Layer 1), inside the working directory:**
```bash
cd "<workdir-path>" && python3 "${SKILL_DIR}/../video-perceive/scripts/perceive_single.py" "<url>"
```
Capture stdout. It prints a line `[perceive_single] -> <path>/_layer1` on
success -- that `<path>` (the printed line's parent of `_layer1`) is
`NOTE_DIR` for this video, and `NOTE_DIR`'s own folder name is `NOTE_STEM`
(e.g. `2026-08-26_some-video-title`). If it exits non-zero, record this video
as **failed**, skip straight to the next video (do not mark it done, do not
delete anything that wasn't created), and continue the loop -- one bad/gated
video must not stop the whole batch.

**b. Understand + write (Layer 2):** invoke the `video-summary` skill on that
video's `_layer1` folder with the requested format:
```
Skill: video-summary
args: "<NOTE_DIR>/_layer1" <format>
```
This produces `<NOTE_DIR>/<NOTE_STEM>.md` (and, if `--format html`, also
`<NOTE_DIR>/<NOTE_STEM>.html`, rendered from the `.md`).

**c. Deliver only the final file:**
```bash
cp "<NOTE_DIR>/<NOTE_STEM>.<format>" "<out>/<NOTE_STEM>.<format>"
```
Only the requested format's file is copied out -- if `--format html`, copy
just the `.html`, not the intermediate `.md` that produced it.

**d. Clean the working directory for this video:**
```bash
rm -rf "<NOTE_DIR>"
```
This removes `_layer1/`, `layer2-temp/`, and the in-progress note together --
nothing about this video survives except the file already copied out in (c).

**e. Mark done:**
```bash
python3 "${SKILL_DIR}/scripts/flow.py" mark-done "<out>" -- "<id>"
```
The `--` before `<id>` is required, not optional -- YouTube video IDs can
start with a `-` (e.g. `-woNvSluePQ`), which argparse would otherwise read as
a flag.

## Step 4 -- tear down and report

```bash
python3 "${SKILL_DIR}/scripts/flow.py" workdir-destroy "<workdir-path>" "<kind>"
```
Then tell the user, plainly: how many notes were written (with their
filenames/paths), how many were skipped as already-done, and, for any
failures, which video (title) and why (`perceive_single.py`'s stderr tail).

## Non-negotiables
- **Never** leave a video's `_layer1`/`layer2-temp` behind in the working
  directory once that video's note is copied out (or once it's failed) --
  process one video fully, clean it, only then move to the next.
- **Never** write anything but the final note file(s) to `--out`, besides the
  skill's own `.video-flow-processed.log`.
- **Never** touch `video-perceive`'s or `video-summary`'s own files.
- If the working directory cannot be created at all (RAM disk **and** plain
  temp directory both fail), stop and report it -- do not silently fall back
  to processing directly in `--out`.
