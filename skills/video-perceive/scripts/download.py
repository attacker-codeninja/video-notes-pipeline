"""Fetch the video (URL via yt-dlp, or just resolve a local path) and pull
platform captions when the source is a URL.

Caption language selection is not hardcoded to English. Found by testing: a
video's spoken language (per yt-dlp's own video-metadata) was Hindi, but this
pipeline only ever fetched English captions — which turned out to be a
*translated* track, not a transcript. Comparing a translation against
same-audio Whisper output word-for-word is meaningless (different languages
always "disagree"), so the pipeline now fetches the caption in the video's
actual spoken language first (real same-language verification against
Whisper becomes possible) and separately keeps an English caption, when one
exists and differs, as a human-readable translation — not used for accuracy
checking, but not thrown away either.
"""
from __future__ import annotations

from pathlib import Path

from common import run, log, is_url


def _get_spoken_language(base_cmd: list, source: str) -> str | None:
    r = run(base_cmd + ["--skip-download", "--print", "%(language)s", source], check=False)
    lang = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    if not lang or lang == "NA":
        return None
    # yt-dlp can return a locale-style tag ("en-US"); Whisper's --language wants
    # the bare 2-letter code ("en"). Found by testing: passing "en-US" straight
    # through made mlx_whisper reject it outright (not in its known language list).
    return lang.split("-")[0].lower()


def _fetch_captions_for_lang(base_cmd: list, source: str, out_dir: Path, lang: str, tag: str) -> dict:
    """Tries manual (human-authored) captions first, then auto-generated, for
    one specific language. Returns {"manual": [paths], "auto": [paths]}."""
    result = {"manual": [], "auto": []}

    run(base_cmd + [
        "--skip-download", "--write-subs", "--no-write-auto-subs",
        "--sub-langs", f"{lang}.*,{lang}", "--sub-format", "vtt", source,
    ], check=False)
    found = sorted(out_dir.glob("source.*.vtt"))
    if found:
        for f in found:
            f.rename(out_dir / f"{tag}_manual_captions{f.suffix}")
        result["manual"] = sorted(str(p) for p in out_dir.glob(f"{tag}_manual_captions*.vtt"))
        return result

    run(base_cmd + [
        "--skip-download", "--write-auto-subs", "--no-write-subs",
        "--sub-langs", f"{lang}.*,{lang}", "--sub-format", "vtt", source,
    ], check=False)
    found = sorted(out_dir.glob("source.*.vtt"))
    if found:
        for f in found:
            f.rename(out_dir / f"{tag}_auto_captions{f.suffix}")
        result["auto"] = sorted(str(p) for p in out_dir.glob(f"{tag}_auto_captions*.vtt"))
    return result


_SEP = "\x1f"  # unit separator — won't collide with real title/id text


def expand_source(source: str, cookies: str | None = None, limit: int | None = None,
                   start: int | None = None) -> list:
    """Resolves a source into a flat list of {"url", "id", "title"} entries —
    one entry for a single video, many for a playlist or a channel/user URL.
    Uses yt-dlp's own --flat-playlist listing (metadata only, no video
    downloaded) so a plain video URL and a playlist/channel URL can be handled
    by the exact same call: yt-dlp treats a lone video as a "playlist of one"
    under --flat-playlist and returns one line either way.

    `limit` caps it at --playlist-end, so a large channel's metadata listing
    itself is bounded, not just the resulting Python list — useful for testing
    the batch pipeline on a couple of videos instead of an entire channel.

    `start` (1-indexed, matches yt-dlp's --playlist-start) lets a large
    channel/playlist be worked through in batches — e.g. start=11, limit=20
    resolves entries 11-20 without yt-dlp needing to enumerate or download
    anything from the entries before them."""
    if not is_url(source):
        return [{"url": source, "id": None, "title": None}]

    cmd = ["yt-dlp", "--flat-playlist", "--skip-download",
           "--print", f"%(id)s{_SEP}%(title)s{_SEP}%(webpage_url)s", source]
    if start:
        cmd += ["--playlist-start", str(start)]
    if limit:
        cmd += ["--playlist-end", str(limit)]
    if cookies:
        cmd += ["--cookies", cookies]
    r = run(cmd, check=False)
    entries = []
    for line in r.stdout.splitlines():
        parts = line.split(_SEP)
        if len(parts) != 3 or not parts[2]:
            continue
        entries.append({"id": parts[0] or None, "title": parts[1] or None, "url": parts[2]})
    if not entries:
        raise RuntimeError(f"yt-dlp could not resolve any video from source: {source}\n{r.stderr[-800:]}")
    return entries


def fetch(source: str, out_dir: Path, cookies: str | None = None) -> dict:
    """Returns {"video_path": str, "manual_captions": [...], "auto_captions": [...],
    "translation_manual_captions": [...], "translation_auto_captions": [...],
    "spoken_language": str|None} — the first four keys hold whichever caption
    track matched the video's actual spoken language; the "translation_*" keys
    hold an English track ONLY when it exists and is a different language
    (kept for readability, never used for literal-accuracy verification)."""
    if not is_url(source):
        p = Path(source).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(f"Local file not found: {source}")
        return {"video_path": str(p), "manual_captions": [], "auto_captions": [],
                "translation_manual_captions": [], "translation_auto_captions": [],
                "spoken_language": None}

    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "source.%(ext)s"

    base_cmd = ["yt-dlp", "--no-playlist", "-o", str(target),
                "--extractor-args", "youtube:player_client=android"]
    if cookies:
        base_cmd += ["--cookies", cookies]

    spoken_lang = _get_spoken_language(base_cmd, source)
    log(f"video's stated spoken language: {spoken_lang or 'unknown'}")

    native = {"manual": [], "auto": []}
    if spoken_lang:
        log(f"checking for captions in the spoken language ({spoken_lang})...")
        native = _fetch_captions_for_lang(base_cmd, source, out_dir, spoken_lang, "native")

    translation = {"manual": [], "auto": []}
    if spoken_lang != "en":
        log("checking for an English caption track (kept as translation reference only)...")
        translation = _fetch_captions_for_lang(base_cmd, source, out_dir, "en", "translation")

    if not spoken_lang and not native["manual"] and not native["auto"]:
        # No language metadata at all — fall back to the old English-first
        # behavior so a video with no language tag still gets SOME caption.
        log("no spoken-language metadata — falling back to English captions...")
        native = _fetch_captions_for_lang(base_cmd, source, out_dir, "en", "native")
        translation = {"manual": [], "auto": []}

    log("downloading video...")
    run(base_cmd + [
        "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b", source,
    ])
    video_files = [f for f in out_dir.glob("source.*")
                   if f.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov")]
    if not video_files:
        raise RuntimeError("yt-dlp did not produce a video file")

    return {
        "video_path": str(video_files[0]),
        "manual_captions": native["manual"],
        "auto_captions": native["auto"],
        "translation_manual_captions": translation["manual"],
        "translation_auto_captions": translation["auto"],
        "spoken_language": spoken_lang,
    }
