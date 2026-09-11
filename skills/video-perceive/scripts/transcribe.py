"""Transcript orchestration.

NOTHING GETS SKIPPED JUST BECAUSE A "BETTER" SOURCE EXISTS. Earlier versions of
this pipeline used captions as a waterfall — first hit wins, stop there — on the
assumption that a higher-priority source (captions) didn't need independent
verification. That assumption is wrong and was called out directly: captions can
still be wrong, and "we found a trustworthy-looking source so we didn't bother
checking it against anything else" is exactly the kind of shortcut this pipeline
exists to not take. So now: if captions exist AND a local Whisper engine is
available, BOTH run, always, for every segment — not just when something looks
suspicious. Caption text remains the default `text` field (still the more
reliable convention on average), but it is cross-checked against fully
independent ASR output (`independent_check`), and disagreement downgrades
confidence and gets surfaced to Layer 2 like anything else. The only two things
that skip a whisper pass at all are `--no-transcribe` (explicit user request)
and no local engine being installed (a real capability limit, not a judgment
call about whether it's "worth it").

Source priority for which text becomes the primary `text` field (see
subtitles.py for 1-4):
  1-4. captions (sidecar / embedded / manual / auto)
  5.   local Whisper (only when no caption source exists at all)
This is a tie-break for display, not a decision about what gets checked.

Whisper path — evidence-based design, not a guess:
Testing this pipeline against a known sentence showed that running two
SAME-SIZE models (mlx "base" vs openai "base") produced the exact same
mistranscription — same training recipe, same capacity, same blind spot.
Running a SMALL model against a MEDIUM model on the same clip, by contrast,
diverged exactly on the words the small model got wrong, and the medium
model's version was correct. So the design here is NOT "primary engine,
verify only if it says it's unsure" (that only catches acoustic uncertainty,
not confident wrongness). It's: run a fast small-model pass AND a slower
medium-model pass over every segment by default, diff them, and prefer the
larger model's text on disagreement — while still surfacing both to Claude
(Layer 2) instead of silently picking one. Confidence scoring
(avg_logprob / no_speech_prob / compression_ratio) is an ADDITIONAL signal on
top of this, not the only one. `--fast` skips the second pass for users who
want speed over scrutiny.
"""
from __future__ import annotations

import difflib
from pathlib import Path

import ocr
import subtitles
import whisper_engines
from common import log, fmt_ts

MIN_SPEECH_COVERAGE = 0.2  # a segment needs at least this much of its duration
                            # covered by VAD-detected speech to not be flagged.
                            # Low, on purpose: normal speech has real pauses too
                            # (see apply_mechanical_crosschecks) — this only
                            # catches segments with almost NO detected voice.

LOW_LOGPROB = -0.8
HIGH_NO_SPEECH = 0.5
HIGH_COMPRESSION = 2.4
# Word-level, not char-level: a 9-of-10-words-right sentence still scores ~0.9 on
# whole-string char similarity, which silently hides the one word that matters
# (found by testing — "...perceived by applying" vs "...perceived by pline" scored
# 0.95 on char ratio despite differing in the one content-bearing word). Requiring
# an exact word-for-word match to call it "agree" means any single differing word
# gets surfaced, which is the point — a mechanical pass has no way to know which
# word matters more, so it should not be the one deciding "close enough."
AGREE_RATIO = 1.0

# Caption-vs-independent-ASR agreement threshold is looser than AGREE_RATIO on
# purpose: captions and Whisper are two genuinely different processes with
# different conventions (punctuation, filler words, "we've" vs "we have") that
# will differ in wording even when both are substantively correct. AGREE_RATIO
# (exact match) is right for same-engine-family small-vs-medium comparison,
# where any difference at all is informative. Here it would just flag almost
# every segment as "disagreement" on noise, burying the real ones.
CROSS_SOURCE_AGREE_RATIO = 0.7


def _mark_caption_segments(resolved: dict) -> list:
    out = []
    for seg in resolved["segments"]:
        out.append({
            "start": seg["start"], "end": seg["end"], "text": seg["text"],
            "source": resolved["source"], "engine": None, "verify_engine": None,
            "confidence": "caption", "cross_check": "not_applicable",
            "alt_text": None, "words": [],
            "audio_check": "not_checked", "frame_ocr_hint": None,
            "independent_check": None, "language": resolved.get("language"),
        })
    return out


def _risk_flags(seg: dict) -> list:
    flags = []
    lp = seg.get("avg_logprob")
    nsp = seg.get("no_speech_prob")
    cr = seg.get("compression_ratio")
    if lp is not None and lp < LOW_LOGPROB:
        flags.append("low_avg_logprob")
    if nsp is not None and nsp > HIGH_NO_SPEECH:
        flags.append("high_no_speech_prob")
    if cr is not None and cr > HIGH_COMPRESSION:
        flags.append("high_compression_ratio")
    return flags


def _overlap(a_start, a_end, b_start, b_end) -> float:
    lo = max(a_start, b_start)
    hi = min(a_end, b_end)
    return max(0.0, hi - lo)


def _find_match(seg: dict, others: list) -> dict | None:
    best, best_overlap = None, 0.0
    for o in others:
        ov = _overlap(seg["start"], seg["end"], o["start"], o["end"])
        if ov > best_overlap:
            best, best_overlap = o, ov
    return best


def _norm_words(text: str) -> list:
    cleaned = "".join(c.lower() for c in text if c.isalnum() or c.isspace())
    return cleaned.split()


def _run_whisper(engine: str, audio_path: str, work_dir: Path, speech_intervals: list, **kwargs) -> list:
    """Chunked-on-VAD-speech transcription when speech_intervals are available
    (see whisper_engines.transcribe_chunked — fixes a real long-form accuracy
    drift found by testing), falling back to a single whole-file call only
    when VAD wasn't available at all."""
    if speech_intervals:
        return whisper_engines.transcribe_chunked(engine, audio_path, work_dir, speech_intervals, **kwargs)
    log("  (no VAD speech intervals available — falling back to a single whole-file pass, "
        "which is more prone to long-form accuracy drift on long audio)")
    return whisper_engines.transcribe(engine, audio_path, work_dir, **kwargs)


def _whisper_pass(audio_16k_path: str, work_dir: Path, primary_engine: str, fast: bool,
                   language: str = None, speech_intervals: list = None) -> list:
    primary_model = whisper_engines.PRIMARY_MODEL.get(primary_engine)
    lang_note = f", language={language}" if language else " (auto-detect language)"
    log(f"pass 1 (fast, primary): {primary_engine} / {primary_model}{lang_note}")
    primary_segments = _run_whisper(
        primary_engine, audio_16k_path, work_dir / "pass_primary", speech_intervals or [],
        model=primary_model, language=language)

    if fast:
        out = []
        for seg in primary_segments:
            flags = _risk_flags(seg)
            out.append({
                "start": seg["start"], "end": seg["end"], "text": seg["text"],
                "source": "whisper_local", "engine": f"{primary_engine}:{primary_model}",
                "verify_engine": None,
                "confidence": "low" if flags else "high",
                "cross_check": f"skipped_fast_mode ({', '.join(flags)})" if flags else "skipped_fast_mode",
                "alt_text": None, "words": seg.get("words", []),
                "audio_check": "not_checked", "frame_ocr_hint": None,
                "independent_check": None, "language": seg.get("detected_language"),
                "translation": None,
            })
        return out

    verify_model = whisper_engines.VERIFY_MODEL.get(primary_engine)
    log(f"pass 2 (slower, verify): {primary_engine} / {verify_model}{lang_note}")
    verify_segments = _run_whisper(
        primary_engine, audio_16k_path, work_dir / "pass_verify", speech_intervals or [],
        model=verify_model, language=language)

    out = []
    for seg in primary_segments:
        match = _find_match(seg, verify_segments)
        primary_flags = _risk_flags(seg)
        record = {
            "start": seg["start"], "end": seg["end"],
            "source": "whisper_local", "engine": f"{primary_engine}:{whisper_engines.PRIMARY_MODEL[primary_engine]}",
            "verify_engine": f"{primary_engine}:{verify_model}" if match else None,
            "words": seg.get("words", []),
            "audio_check": "not_checked", "frame_ocr_hint": None,
            "independent_check": None, "translation": None,
        }
        record["language"] = seg.get("detected_language")
        if match is None:
            record.update(text=seg["text"], confidence="low" if primary_flags else "high",
                          cross_check="no_verify_match", alt_text=None)
        else:
            verify_flags = _risk_flags(match)
            ratio = difflib.SequenceMatcher(None, _norm_words(seg["text"]), _norm_words(match["text"])).ratio()
            if ratio >= AGREE_RATIO:
                record.update(text=match["text"], confidence="low" if (primary_flags or verify_flags) else "high",
                              cross_check=f"agree (ratio={ratio:.2f})", alt_text=None)
            else:
                # Models disagree. "Bigger model wins" was the original rule, but
                # testing this against a real video found the bigger (verify) model
                # can itself fail — a compression_ratio of 17 (repeated "ॐ ॐ ॐ..."),
                # a classic Whisper hallucination-loop artifact, while the smaller
                # model's own risk flags were clean. A model's SIZE says nothing
                # about whether THIS SPECIFIC output is garbage — only that
                # model's own confidence signals do. So: check both models' own
                # signals and prefer whichever one looks healthy; if both look
                # bad, trust neither and say so explicitly.
                if verify_flags and not primary_flags:
                    log(f"  DISAGREE [{fmt_ts(seg['start'])}] verify model flagged ({', '.join(verify_flags)}), "
                        f"using primary instead: small={seg['text']!r} (rejected medium={match['text']!r})")
                    record.update(text=seg["text"], confidence="low",
                                  cross_check=f"disagree (ratio={ratio:.2f}, resolved_to=primary_model — verify model was flagged: {', '.join(verify_flags)})",
                                  alt_text=match["text"])
                elif primary_flags and not verify_flags:
                    log(f"  DISAGREE [{fmt_ts(seg['start'])}] small={seg['text']!r} vs medium={match['text']!r} (ratio={ratio:.2f})")
                    record.update(text=match["text"], confidence="low",
                                  cross_check=f"disagree (ratio={ratio:.2f}, resolved_to=verify_model)",
                                  alt_text=seg["text"])
                elif primary_flags and verify_flags:
                    log(f"  DISAGREE [{fmt_ts(seg['start'])}] BOTH models flagged — small={seg['text']!r} "
                        f"({', '.join(primary_flags)}) vs medium={match['text']!r} ({', '.join(verify_flags)})")
                    record.update(text=match["text"], confidence="low",
                                  cross_check=f"disagree (ratio={ratio:.2f}, BOTH models flagged, neither trustworthy — "
                                              f"small: {', '.join(primary_flags)}; medium: {', '.join(verify_flags)})",
                                  alt_text=seg["text"])
                else:
                    # Neither model flagged itself as risky — a genuine wording
                    # difference on ambiguous audio, not a hallucination. This is
                    # the case size-diversity testing was actually designed for;
                    # the larger model's judgment is the tie-break.
                    log(f"  DISAGREE [{fmt_ts(seg['start'])}] small={seg['text']!r} vs medium={match['text']!r} (ratio={ratio:.2f})")
                    record.update(text=match["text"], confidence="low",
                                  cross_check=f"disagree (ratio={ratio:.2f}, resolved_to=verify_model)",
                                  alt_text=seg["text"])
        out.append(record)
    return out


def build_transcript(video_path: str, out_dir: Path, manual_captions: list, auto_captions: list,
                      audio_16k_path: str | None, engine_pref: str | None,
                      no_transcribe: bool, fast: bool, language: str | None = None,
                      speech_intervals: list | None = None,
                      translation_manual_captions: list | None = None,
                      translation_auto_captions: list | None = None) -> list:
    if no_transcribe:
        return []

    resolved = subtitles.resolve(video_path, out_dir, manual_captions, auto_captions)
    caption_segments = _mark_caption_segments(resolved) if resolved is not None else None

    # A same-language caption is the literal-accuracy source (compared against
    # Whisper below). A translated caption, when one was also fetched (see
    # download.py), is attached to each segment as read-along context — never
    # used to judge accuracy, since comparing two languages word-for-word
    # proves nothing (see the different_language handling further down).
    translation_path = (translation_manual_captions or translation_auto_captions or [None])[0]
    if caption_segments and translation_path:
        translation_segments = subtitles.parse_vtt_or_srt(translation_path)
        for cap in caption_segments:
            match = max(
                translation_segments,
                key=lambda t: _overlap(cap["start"], cap["end"], t["start"], t["end"]),
                default=None,
            )
            cap["translation"] = match["text"] if match and _overlap(cap["start"], cap["end"], match["start"], match["end"]) > 0 else None
    elif caption_segments:
        for cap in caption_segments:
            cap["translation"] = None

    # `language` here must come from an explicit --language flag or the video's
    # own metadata (yt-dlp's %(language)s — see download.py) — NEVER from a
    # caption's own stated language. Those are different signals with different
    # trust levels: a caption's language tag can be a *translation*'s language
    # (YouTube auto-translated caption tracks are labeled with the translated
    # language, not the video's actual spoken language) — found on a real video
    # where forcing the caption's "en" tag onto Whisper made it mistranscribe
    # actual Hindi speech into fluent-sounding-but-wrong English. The video's
    # own declared spoken-language metadata doesn't have that problem, which is
    # why download.py now fetches captions IN that language first instead of
    # defaulting to English.
    whisper_language = language

    whisper_segments = None
    engines = whisper_engines.available_engines() if audio_16k_path else []
    if audio_16k_path and engines:
        primary = engine_pref if engine_pref in engines else engines[0]
        work_dir = out_dir / "_whisper_work"
        whisper_segments = _whisper_pass(audio_16k_path, work_dir, primary, fast,
                                          language=whisper_language, speech_intervals=speech_intervals)
        import shutil
        shutil.rmtree(work_dir, ignore_errors=True)
    elif audio_16k_path and not engines:
        log("no local Whisper engine available — cannot independently cross-check captions"
            if caption_segments else "no local Whisper engine available — no transcript possible")
    elif not audio_16k_path:
        log("no audio stream — Whisper cross-check not possible")

    if caption_segments and whisper_segments:
        log("cross-checking captions against independent Whisper transcription...")
        return _merge_caption_and_whisper(caption_segments, whisper_segments)
    if caption_segments:
        for seg in caption_segments:
            seg["independent_check"] = {"method": "whisper_asr", "match": "not_available (no local engine / no audio)"}
        return caption_segments
    if whisper_segments:
        return whisper_segments

    log("no captions and no usable audio — nothing to transcribe")
    return []


def _merge_caption_and_whisper(caption_segments: list, whisper_segments: list) -> list:
    """Captions stay the displayed `text` (still the better convention on
    average), but every single one gets checked against fully independent ASR
    output covering the same time range — agreement/disagreement recorded in
    `independent_check`, not silently assumed just because captions are
    normally reliable.

    Language mismatch is checked FIRST, before comparing wording at all. A
    caption's language tag can be a translation, not the video's actual
    spoken language (YouTube auto-translated caption tracks are labeled with
    the translated language) — found by testing: an English caption existed
    for a video whose spoken language (per the video's own metadata) was
    Hindi. Word-for-word comparison across two different languages will
    disagree on every single segment regardless of whether either is
    accurate, so that comparison is skipped and labeled honestly instead of
    reported as a wall of "disagreements" that isn't actually evidence of
    anything being wrong."""
    caption_lang = caption_segments[0].get("language") if caption_segments else None

    for cap in caption_segments:
        overlapping = sorted(
            (w for w in whisper_segments if _overlap(cap["start"], cap["end"], w["start"], w["end"]) > 0),
            key=lambda w: w["start"],
        )
        if not overlapping:
            cap["independent_check"] = {"method": "whisper_asr", "match": "no_overlapping_audio_segment"}
            continue

        whisper_lang = next((w.get("language") for w in overlapping if w.get("language")), None)
        if caption_lang and whisper_lang and caption_lang != whisper_lang:
            # Language mismatch and Whisper's own reliability are two separate,
            # independently-true facts — don't let one hide the other. A
            # different-language Whisper segment can ALSO be garbage in its own
            # right (the repetition-loop hallucination found by testing doesn't
            # care what language it's looping in — "ॐ ॐ ॐ..." showed up here
            # too). Say both explicitly instead of presenting whichever text
            # happens to be there as if it were clean.
            whisper_unreliable = any(w.get("confidence") == "low" for w in overlapping)
            note = ("; NOTE: the Whisper output itself was ALSO flagged low-confidence/unreliable "
                    "for this span (see the overlapping whisper_local segment's own cross_check) — "
                    "this is not just a translation mismatch" if whisper_unreliable else "")
            cap["independent_check"] = {
                "method": "whisper_asr", "engine": ", ".join(sorted({w["engine"] for w in overlapping if w.get("engine")})),
                "text": " ".join(w["text"] for w in overlapping),
                "caption_language": caption_lang, "spoken_language": whisper_lang,
                "whisper_reliable": not whisper_unreliable,
                "match": f"different_language (caption={caption_lang}, audio_detected={whisper_lang}) "
                         f"— likely a translated caption track, wording not comparable across languages{note}",
            }
            continue

        combined_text = " ".join(w["text"] for w in overlapping)
        engines_used = sorted({w["engine"] for w in overlapping if w.get("engine")})
        ratio = difflib.SequenceMatcher(None, _norm_words(cap["text"]), _norm_words(combined_text)).ratio()

        if ratio >= CROSS_SOURCE_AGREE_RATIO:
            cap["independent_check"] = {
                "method": "whisper_asr", "engine": ", ".join(engines_used),
                "text": combined_text, "match": f"agree (ratio={ratio:.2f})",
            }
        else:
            log(f"  CAPTION vs WHISPER DISAGREE [{fmt_ts(cap['start'])}] "
                f"caption={cap['text']!r} vs whisper={combined_text!r} (ratio={ratio:.2f})")
            cap["independent_check"] = {
                "method": "whisper_asr", "engine": ", ".join(engines_used),
                "text": combined_text, "match": f"disagree (ratio={ratio:.2f})",
            }
            cap["confidence"] = "low"
    return caption_segments


def apply_mechanical_crosschecks(segments: list, frame_records: list, speech_intervals: list) -> None:
    """Two more independent signals, mutating `segments` in place — this is what
    makes the check actually cross audio and frames instead of stopping at
    transcript-vs-transcript:

    1. Voice-activity coverage: Silero VAD (see vad.py) reports where a human
       voice was actually detected, independent of any Whisper model AND more
       reliable than a raw volume threshold. If a segment has almost no
       detected speech overlapping it, that's a strong, non-linguistic signal
       the transcript there is a hallucination, not just a wrong guess.
       (An earlier version of this check used ffmpeg's amplitude-based
       `silencedetect` and summed silence gaps within a segment — tested
       against a real captioned video, it flagged a line as "55% silent" that
       was, on inspection, someone talking continuously with a few ordinary
       sub-second breath pauses. VAD models what speech actually looks like
       instead of just measuring volume, so normal pauses inside continuous
       speech don't get miscounted as absence of speech.)
    2. Frame OCR: for anything already flagged (whisper disagreement, low
       confidence, or a speech-coverage mismatch), pull on-screen text from
       the nearest frame(s) and check whether it shares a distinctive word
       with either transcript candidate. This is real evidence from the video
       itself, computed mechanically, not something Claude has to eyeball for
       every flagged line.
    """
    ocr_cache: dict = {}

    for seg in segments:
        if speech_intervals:
            dur = max(0.001, seg["end"] - seg["start"])
            spoken = sum(_overlap(seg["start"], seg["end"], s, e) for s, e in speech_intervals)
            coverage = min(1.0, spoken / dur)
            if coverage < MIN_SPEECH_COVERAGE:
                seg["audio_check"] = f"no_speech_detected (voice coverage={coverage:.0%} of segment)"
                seg["confidence"] = "low"
            else:
                seg["audio_check"] = f"ok (voice coverage={coverage:.0%})"

        needs_ocr = (
            seg.get("confidence") == "low"
            or "disagree" in str(seg.get("cross_check", ""))
            or "no_speech_detected" in str(seg.get("audio_check", ""))
            or "disagree" in str((seg.get("independent_check") or {}).get("match", ""))
        )
        if not needs_ocr or not frame_records or not ocr.available():
            continue

        candidates = ocr.nearest_frames(frame_records, seg["start"], seg["end"])
        for frame in candidates:
            path = frame["file"]
            if path not in ocr_cache:
                # frame["file"] is stored relative to out_dir; caller passes
                # frame_records with resolved absolute paths already (see watch.py)
                ocr_cache[path] = ocr.read_text(path)
            text = ocr_cache[path]
            if not text:
                continue
            indep = seg.get("independent_check") or {}
            hit_primary = ocr.shares_distinctive_word(text, seg["text"])
            hit_alt = ocr.shares_distinctive_word(text, seg.get("alt_text") or "")
            hit_indep = ocr.shares_distinctive_word(text, indep.get("text") or "")
            if hit_primary or hit_alt or hit_indep:
                supports = "primary" if hit_primary else ("alt_text" if hit_alt else "independent_check")
                seg["frame_ocr_hint"] = {
                    "frame": frame["file"], "ocr_text": text[:200],
                    "supports": supports,
                    "shared_word": hit_primary or hit_alt or hit_indep,
                }
                break
        if seg.get("frame_ocr_hint") is None and candidates:
            # OCR ran but found nothing corroborating either version — say so
            # explicitly rather than leaving it indistinguishable from "not checked"
            seg["frame_ocr_hint"] = {"frame": None, "ocr_text": None, "supports": "no_match", "shared_word": None}


def render_txt(segments: list) -> str:
    lines = []
    for seg in segments:
        tag = ""
        cc = str(seg.get("cross_check", ""))
        indep = seg.get("independent_check") or {}
        if "disagree" in cc:
            tag = f" [VERIFY - small model said: \"{seg.get('alt_text')}\"]"
        elif "disagree" in str(indep.get("match", "")):
            tag = f" [VERIFY - independent Whisper said: \"{indep.get('text')}\"]"
        elif seg.get("confidence") == "low":
            tag = " [VERIFY]"
        line = f"[{fmt_ts(seg['start'])} - {fmt_ts(seg['end'])}]{tag} {seg['text']}"
        if seg.get("translation"):
            line += f"\n    (translation: {seg['translation']})"
        lines.append(line)
    return "\n".join(lines)
