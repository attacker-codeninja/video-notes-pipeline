"""Writes MANIFEST.txt — the entry point Claude reads first."""
from __future__ import annotations

from pathlib import Path

from common import fmt_ts


def write(out_dir: Path, video_path: str, duration: float, frame_records: list, grids: list,
          audio_info: dict, transcript_segments: list) -> None:
    lines = []
    lines.append("VIDEO-PERCEIVE MANIFEST")
    lines.append("=" * 40)
    lines.append(f"source: {video_path}")
    lines.append(f"duration: {fmt_ts(duration)}")
    lines.append("")

    lines.append(f"FRAMES: {len(frame_records)} kept (see frames/, chronological)")
    if grids:
        lines.append(f"GRIDS: {len(grids)} contact sheets (see grids/) — read these instead of individual frames unless you need a close-up")
    lines.append("")

    lines.append("AUDIO:")
    if audio_info.get("has_audio"):
        lines.append(f"  full soundtrack: {Path(audio_info['audio_path']).name}")
        lines.append("  (kept as a first-class output — music/tone/sound effects live here, not just in the transcript)")
    else:
        lines.append("  no audio stream in source")
    lines.append("")

    lines.append(f"TRANSCRIPT: {len(transcript_segments)} segments")
    sources = {}
    low_conf = []
    disagreements = []
    caption_vs_asr_disagreements = []
    different_language = []
    different_language_and_unreliable = []
    silence_mismatches = []
    ocr_hits = []
    not_independently_checked = []
    for i, seg in enumerate(transcript_segments):
        sources[seg["source"]] = sources.get(seg["source"], 0) + 1
        if seg.get("confidence") == "low":
            low_conf.append((i, seg))
        if "disagree" in str(seg.get("cross_check", "")):
            disagreements.append((i, seg))
        if "no_speech_detected" in str(seg.get("audio_check", "")):
            silence_mismatches.append((i, seg))
        hint = seg.get("frame_ocr_hint")
        if hint and hint.get("supports") in ("primary", "alt_text", "independent_check"):
            ocr_hits.append((i, seg))
        indep = seg.get("independent_check")
        if indep and "disagree" in str(indep.get("match", "")):
            caption_vs_asr_disagreements.append((i, seg))
        if indep and "different_language" in str(indep.get("match", "")):
            different_language.append((i, seg))
            if indep.get("whisper_reliable") is False:
                different_language_and_unreliable.append((i, seg))
        if indep and "not_available" in str(indep.get("match", "")):
            not_independently_checked.append((i, seg))
    for src, count in sources.items():
        lines.append(f"  {count} segment(s) from source: {src}")
    lines.append("")

    if different_language:
        indep0 = different_language[0][1]["independent_check"]
        lines.append(f"TRANSLATED CAPTION DETECTED ({len(different_language)}) — caption language differs from the video's spoken language")
        lines.append("-" * 40)
        lines.append(f"Caption language: {indep0.get('caption_language')}  |  Detected spoken language: {indep0.get('spoken_language')}")
        lines.append("This is very likely a translated caption track, not a literal transcript. Word-for-word")
        lines.append("cross-checking against Whisper was skipped for these segments (comparing across languages")
        lines.append("proves nothing) — treat the caption text as a translation/paraphrase, not a verified quote,")
        lines.append("and rely on the independent_check.text field (same-language Whisper output) if you need")
        lines.append("the literal spoken words.")
        if different_language_and_unreliable:
            lines.append("")
            lines.append(f"  Of these, {len(different_language_and_unreliable)} ALSO had a low-confidence/garbage Whisper")
            lines.append("  output for that span (independent_check.whisper_reliable=false) — a separate real")
            lines.append("  problem, not just the language mismatch. For these, neither the caption's literal")
            lines.append("  wording nor Whisper's is verified; lean on frames (2b) for these specifically:")
            for i, seg in different_language_and_unreliable[:10]:
                lines.append(f"    [{fmt_ts(seg['start'])}] caption: \"{seg['text']}\"")
        lines.append("")

    if not_independently_checked:
        lines.append(f"NOT INDEPENDENTLY VERIFIED ({len(not_independently_checked)}) — captions used as-is, no local Whisper engine/audio to cross-check against")
        lines.append("-" * 40)
        lines.append("This is a real capability gap on this run, not a judgment call — treat these with more caution in Layer 2.")
        lines.append("")

    if silence_mismatches:
        lines.append(f"AUDIO MISMATCH ({len(silence_mismatches)}) — transcript claims speech, but voice-activity detection found almost none")
        lines.append("-" * 40)
        lines.append("Silero VAD measured actual voice activity here, independent of any transcription engine.")
        for i, seg in silence_mismatches:
            lines.append(f"  [{fmt_ts(seg['start'])}] \"{seg['text']}\" — {seg.get('audio_check')}")
        lines.append("")

    if ocr_hits:
        lines.append(f"FRAME OCR CORROBORATION ({len(ocr_hits)}) — on-screen text backs one reading")
        lines.append("-" * 40)
        for i, seg in ocr_hits:
            hint = seg["frame_ocr_hint"]
            lines.append(f"  [{fmt_ts(seg['start'])}] frame {hint['frame']} shows \"{hint['ocr_text']}\" — "
                         f"matches the {hint['supports']} reading (shared word: \"{hint['shared_word']}\")")
        lines.append("")

    if caption_vs_asr_disagreements:
        lines.append(f"CAPTION vs INDEPENDENT ASR DISAGREEMENTS ({len(caption_vs_asr_disagreements)}) — two fully independent transcription processes disagree")
        lines.append("-" * 40)
        lines.append("This is stronger evidence than model-size disagreement — caption and Whisper are unrelated pipelines.")
        for i, seg in caption_vs_asr_disagreements:
            indep = seg["independent_check"]
            lines.append(f"  [{fmt_ts(seg['start'])}] caption: \"{seg['text']}\"  |  Whisper ({indep.get('engine')}): \"{indep.get('text')}\"")
        lines.append("")

    if disagreements:
        lines.append(f"DISAGREEMENTS ({len(disagreements)}) — small model vs. medium model gave different text")
        lines.append("-" * 40)
        for i, seg in disagreements:
            lines.append(f"  [{fmt_ts(seg['start'])}] used: \"{seg['text']}\"  |  small model said: \"{seg.get('alt_text')}\"")
        lines.append("")

    if low_conf:
        lines.append(f"OTHER LOW-CONFIDENCE SEGMENTS ({len(low_conf)})")
        lines.append("-" * 40)
        for i, seg in low_conf:
            if (i, seg) in disagreements:
                continue
            lines.append(f"  [{fmt_ts(seg['start'])}] \"{seg['text']}\" — cross_check: {seg.get('cross_check')}")
        lines.append("")

    if low_conf or disagreements or silence_mismatches or caption_vs_asr_disagreements:
        lines.append("LAYER 2 — YOU MUST DO THIS BEFORE ANSWERING (two parts, both required)")
        lines.append("-" * 40)
        lines.append(
            "Layer 1 (this script) already cross-checked the transcript four independent ways:\n"
            "  1. two different-size local models, diffed word-for-word\n"
            "  2. captions against a fully independent Whisper transcription (never skipped just\n"
            "     because captions were found — a higher-priority source still gets verified)\n"
            "  3. the transcript against Silero VAD voice-activity detection\n"
            "  4. the transcript against OCR'd on-screen text from the nearest frame(s)\n"
            "But this pipeline was tested against a known sentence and confirmed something\n"
            "important: two SAME-SIZE models can confidently make the IDENTICAL mistake, and\n"
            "even a small-vs-medium diff can land on a wrong-but-plausible answer. No mechanical\n"
            "signal alone is proof — including the three above. You are the next line of\n"
            "defense, and you have two tools Layer 1 doesn't:\n"
            "\n"
            "  2a. READ THE FULL TRANSCRIPT AS CONTINUOUS TEXT (not just the flagged lines in\n"
            "      isolation) before answering anything. Whisper errors often read as slightly\n"
            "      off English in context even when no engine flagged them — a word that almost\n"
            "      fits but breaks the sentence's logic. If a sentence anywhere in transcript.txt\n"
            "      doesn't parse cleanly, treat it as suspect even if it's not in the lists above.\n"
            "\n"
            "  2b. CHECK FLAGGED SEGMENTS AGAINST THE FRAME(S) AT THAT TIMESTAMP. If on-screen\n"
            "      text/slide/code confirms one reading over the other, use it and say so. If\n"
            "      nothing on screen resolves it, tell the user the line is uncertain instead of\n"
            "      presenting a guess as fact.\n"
            "\n"
            "Do not silently pick a version and move on."
        )
        lines.append("")

    lines.append("TRANSCRIPT SOURCE RELIABILITY (highest to lowest trust — but every tier is still")
    lines.append("cross-checked against independent ASR when a local engine is available, never assumed):")
    lines.append("  sidecar_vtt/srt, embedded_track, manual_caption  >  auto_caption  >  whisper_local (two model sizes agree)  >  whisper_local (disagree/low-confidence, needs Layer 2)")
    lines.append("")
    lines.append("See transcript.json for full structured data: timestamps, word-level timing where")
    lines.append("available, source, engine + verify_engine, confidence, cross_check, alt_text")
    lines.append("(overruled small-model version), independent_check (caption vs. independent Whisper")
    lines.append("agreement), audio_check (voice-activity coverage), and frame_ocr_hint (on-screen")
    lines.append("text corroboration).")
    lines.append("See transcript.txt for a quick plain-text read ([VERIFY] tags on flagged lines).")

    (out_dir / "MANIFEST.txt").write_text("\n".join(lines), encoding="utf-8")
