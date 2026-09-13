# Presentation guidance (NOT templates)

This file does **not** give you a fixed skeleton to fill. The frozen Canonical
Knowledge is already built and validated — your job in Step F is to write it up
**the way a real self-learner writes their own notes after watching a video**:
their own headings, their own heading names, their own order, their own wording,
shaped by *this* video's knowledge — not a house style, not a reused layout.

Two different videos should produce two differently-shaped notes. That variation
is the point. Do not converge on one structure across runs.

The one rule from SKILL.md still holds: **present only what's in the frozen
knowledge, invent nothing.** Everything below is about *shape and voice*, never
about *content* — content is fixed upstream.

---

## FIXED — the only things every note must have

1. **YAML frontmatter, then a metadata block, at the very top.** Fill both from
   Canonical `video`:
   - Frontmatter (Obsidian-vault metadata — see the OBSIDIAN FORMAT section below):
     `title`, `date` (video's upload date if Layer 1 captured it, else today),
     `tags` (2–4 genuinely relevant to this video's subject, not generic filler),
     `aliases: []`.
   - Metadata block (human-readable, right under the H1) is a **table**, not a
     bullet list — two columns, one row per field:
     ```markdown
     | Field | Value |
     |---|---|
     | Video URL | ... |
     | Title | ... |
     | Author / Channel | ... |
     | Length | ... |
     | Language | ... |
     ```
     A literal `|` inside a cell (common in video titles, e.g. "Conversation
     with JakSec | Bug Bounty Hunting") must be escaped as `\|` so it isn't read
     as a column break — `render.py` unescapes it back on output.
   - Any field that is `null` → write `N/A (not present in Layer 1 output)`. Never
     invent a URL or author. If `title` is null but `title_guess` exists, confirm
     it from the title-card frame and use the confirmed text.
2. **Clear, plain English throughout** — whatever language the video is in, the
   notes are always written in English. Explain any term the learner wouldn't
   already know the first time it appears, in one plain in-line phrase, then use it
   normally.
3. **Faithfulness (the "logic" layer):**
   - Every concrete claim (number, name, command, URL, term) maps to a node in
     the frozen knowledge. Nothing added from outside.
   - Opinions stay opinions — "the creator argues…", "in the creator's view…".
     Never promote a `creator_opinion` claim to stated fact.
   - Scopes, qualifications, contradictions stay visible. Don't silently resolve
     a contradiction the video left open.
   - **Uncertainty is woven in, in the learner's own words**, where it's
     relevant — the way a person writes "the exact number wasn't clear here"
     mid-note. A dedicated "Uncertainty" heading is **not** required (and
     usually worse). Unresolved `pending_threads` are stated as still-open,
     never answered.
4. **No filler** — no "in this video we'll learn…", no meta-commentary about
   the note itself, no restating the same point twice, no closing recap that just
   repeats the body.
5. **No transcript dumping.** You're writing understanding, not a cleaned-up
   transcript.
6. **Right after the metadata block, two fixed things come first, in this order,
   before any of the video's own sections:**
   - **A `[!abstract] Quick Summary` callout** — 2-4 plain-prose lines (not
     bulleted) giving instant orientation: what this video is, and what it
     covers. This is the "glance and know" layer — someone reading only this
     callout should get the gist in five seconds.
   - **A `## Summary` section** — a complete bulleted list that covers
     every meaningful point made in the note **below** it (not a teaser, not a
     "top 3" — everything the detailed sections go on to cover). **One blank
     line between consecutive bullets.** `## Summary` is a fixed
     heading name — every heading below it, up to the Ending Deep-Dive Layer
     (item 7), is yours. **The bold rule further down applies exactly as much
     to these bullets as to the body** — a bullet compressing three body
     sentences still needs the load-bearing bold those sentences had. This is
     not the "plain" section — it's the two-layer gist (quick prose, then
     complete bullets) before the full detail begins.

   Only *after* both of these does the video's own detailed write-up begin —
   same full depth and content as always, just positioned below the Quick
   Summary and Summary instead of above them.
7. **At the very end of the note, after the video's own detailed write-up, a
   fixed "Ending Deep-Dive Layer" always comes** — six sub-sections, in this
   order, with these exact heading names (unlike the free body above, these
   names never change per video):

   a. **`## What I Actually Learned`** — the one section where you stop
      reporting the video and start teaching from your own understanding.
      Shift voice: you are now a **top student writing their own revision
      notes**, explaining — in your own words, not the video's — what you
      genuinely internalized. Not a rehash of the Summary; if a
      sentence here could be produced by paraphrasing a transcript line,
      rewrite it as your own synthesis instead. Go deep: break it into your
      own named sub-sections (`###`), and wrap each real insight in a
      callout — `[!tip]`/`[!important]` for a genuine "aha, so that's why"
      point, `[!example]` where you illustrate it with the video's own
      example. Multiple callouts, multiple sub-sections — this is the
      deepest part of the note, not a summary of one.
   b. **`## Interview Q&A`** — the same knowledge, drilled as recall practice.
      **Exhaustive, never a sample.** Go through the frozen knowledge and
      generate a genuine interview question for every concept, command,
      claim, number, gotcha, and distinction it contains — not just the 4-5
      headline ones. A dense technical video should produce a long Q&A
      section (15-30+ pairs is normal for a demo-heavy video); a short
      single-idea video produces fewer, but never artificially capped and
      never padded with near-duplicate rephrasings of the same question
      either. Grouped into topic sub-sections (`###`), each Q&A pair as its
      own `[!question] <the question>` callout followed by a full, detailed
      answer (not one line) — as if answering out loud in an interview.
      Questions come only from what the video actually covered; never invent
      knowledge the video didn't give you to answer a question you posed.
      Before moving on, check: could someone study *only* this section and
      be able to speak confidently on everything the video taught? If a
      concept/command/number from the body has no matching question here,
      add one.
   c. **`## Code Walkthrough`** — **only if the video actually shows/dictates
      code, commands, or config.** Skip this heading entirely otherwise (no
      empty section). Every distinct code block or command gets three parts,
      in order: (1) the code itself, in a fenced block with a language tag;
      (2) a **plain-English, line-by-line or flag-by-flag explanation** right
      under it — what each part does and why, written for someone who's
      never seen this syntax before (same zero-assumed-knowledge rule as
      ROLE) — never just the code with no walkthrough; (3) an `[!example]`
      **proof** callout citing what the video actually showed as the result
      (the on-screen output, the frame evidence) so the code isn't asserted,
      it's demonstrated. Goal: a reader could type this themselves and
      understand what every line/flag accomplishes, not just copy-paste it.
   d. **`## Mind Map`** — **only if the video's concepts/relationships are
      rich enough to earn one** (skip for a simple single-idea video). One
      **consolidated** Mermaid diagram of the *whole* video's structure — not
      a repeat of a smaller diagram already used in the body — built strictly
      from Canonical Knowledge relationships.
   e. **`## Formulas`** — **only if the video actually contains a
      formula/equation.** Each one in a math block (`$$...$$`), with a
      one-line plain-English explanation of what each symbol means.
   f. **`## Quick Revision`** — the last section, always present. One
      `[!abstract] Quick Revision` callout holding a short, dense bullet list
      — **opposite of the Summary**: no elaboration, just
      `**keyword**: crisp recall phrase` per line, scannable in one pass right
      before an exam or interview. Nothing new — only callbacks to terms and
      numbers already established above.

   The conditional sub-sections (c, d, e) are skipped cleanly when they don't
   apply — never a heading with "N/A" under it. (a), (b), and (f) are never
   skipped, even for a short video — they just stay proportionally short.
8. **Written per the `obsidian-md-formatter` skill's syntax** (frontmatter, callouts,
   tables, footnotes, Mermaid) — see OBSIDIAN FORMAT below. This governs *syntax*
   only, never content or which sections exist.

Everything else — the detailed sections *between* the Summary and the
Ending Deep-Dive Layer, their names, their order, paragraph vs bullet vs
table, whether there's a diagram — **you decide, per video.** The Ending
Deep-Dive Layer's own six heading names (item 7) are fixed and always in that
order, the same as Quick Summary / Summary are.

---

## OBSIDIAN FORMAT — syntax layer, on top of everything above

The note's *shape* (headings, order, voice) stays entirely yours per the ROLE and
METHOD below — this section only governs *how it's typeset* so the file drops into
an Obsidian vault with zero reformatting. Before writing, load the
`obsidian-md-formatter` skill (via the Skill tool) for the full cheatsheet and the
valid callout-type list; the essentials:

- **Frontmatter** at the very top (see FIXED §1).
- **Callouts** (`> [!type] optional title`) where they earn their place — a warning
  the video gives, a recommendation, a definition/summary, a memorable creator
  quote (`[!quote]`). Don't wrap ordinary prose in a callout just to look styled;
  most of the note stays plain paragraphs/lists/headings.
- **Tables** for genuine comparisons (options, positions, before/after).
- **Footnotes** (`[^1]`) if the video cites an external source worth naming.
- **Wiki-links** (`[[...]]`) only for a genuine cross-reference — a standalone
  video note usually has none; don't invent links to make it look connected.
- **Mermaid** exactly as already described in this file — unchanged by this
  section, and it still needs to actually render (`html` output renders it; keep
  diagrams strictly from Canonical Knowledge).
- Run the obsidian-md-formatter validation checklist before finalizing (single H1,
  properly nested headings, code blocks with language tags, only valid callout
  types, no excluded syntax).

---

## ROLE you write as

> An absolute-beginner self-learner who just watched this video and is writing
> study notes for their future self. Not an expert in the subject — just genuinely
> interested in learning it. Topic is irrelevant to the treatment (tech, cooking,
> finance, history, law — same approach). Zero assumed knowledge: the first time a
> term appears, explain it in one plain in-line line, then use it.

The voice, the exact heading names, the structure, the formatting choices are
**re-decided for each video** from its knowledge — do not lock a personal style.

---

## METHOD — how to go from frozen knowledge to the note

Run these five stages in order. This is a reasoning procedure, not section
headings for the output.

1. **Grasp** — Read the `state.py select` output (the full frozen knowledge). What
   is this video actually about? Which P0 / high-centrality nodes are the spine,
   which nodes are only supporting? What *type* of video is it (tutorial, lecture,
   talk, interview, debate, review, story, walkthrough, demo)? Every meaningful
   node goes into the note — `priority_effective` only tells you what to lead with
   and what to keep brief, never what to drop.

2. **Spine** — Does the video carry its own organizing structure? (numbered
   points, chapters, an agenda/roadmap slide, a before→after, a problem→solution
   arc, a chronological build.) **If yes → mirror it**, and name your headings in
   the video's own terms (e.g. "Lesson 3 — Chase bad leads too", not
   "Main Idea 3"). **If no → group the concepts by their relationships** into a
   natural outline a note-taker would use.

3. **Layout** — Decide the sections and their names now. Pick formatting devices
   from the menu below only where the content genuinely calls for them. A simple
   talk may need none; a code tutorial needs code blocks. Do not add a device to
   look thorough.

4. **Write** — Right after the metadata block, write the fixed `[!abstract]
   Quick Summary` callout and the fixed `## Summary` bullets (blank
   line between each) first — by this point the full understanding is already
   grasped, so both are straightforward to write; they just land at the top
   of the file, not the bottom. Then write the detailed sections below, in
   the learner's voice. Cover every meaningful point; the note's length
   follows the video's density, not a target. Explain each new term inline on
   first use. Weave in uncertainty where relevant. Keep creator opinions
   marked as opinions. **Finally, write the fixed Ending Deep-Dive Layer**
   (FIXED §7): `## What I Actually Learned` (your own synthesis, top-student
   voice), `## Interview Q&A` (exhaustive — every concept/command/claim/number
   gets its own question, not a sample of headline ones), `## Code Walkthrough`
   (every command explained line-by-line, not just shown) / `## Mind Map` /
   `## Formulas` (each only if earned), and `## Quick Revision` last, always.

5. **Honesty-check** — Second pass over your draft: every concrete claim traces to
   a node; nothing invented; no opinion hardened into fact; scopes/qualifications
   intact; hedged things still hedged; open threads still open; clear, correct
   English throughout — no leftover jargon left unexplained; **every
   `## Summary` bullet carries its own 1–3 bold spans** on the numbers/
   terms/outcomes that make it (see "Bold — what earns it" below) — a bullet
   with no bold while its neighbors have plenty means something got flattened
   on the way in. Also check the Ending Deep-Dive Layer specifically:
   `## What I Actually Learned` isn't just the Summary reworded (it
   should read as synthesis, not paraphrase); `## Interview Q&A` is
   **exhaustive** — walk the frozen knowledge node by node and confirm every
   concept/command/claim/number has a question covering it, not just a
   handful of headline ones — and every answer is fully detailed, not a
   one-liner; `## Code Walkthrough`, if present, explains **every** code
   block/command line-by-line or flag-by-flag (not just code + proof with no
   walkthrough) — conditional sections (Code/Mind Map/Formulas) are present
   only where earned and cleanly absent otherwise; `## Quick Revision` is
   genuinely terse (no elaboration sneaking back in). Fix and re-check. (This
   is the `rubrics.md §8` validation — it checks
   fidelity to Canonical Knowledge, not truth-vs-reality.)

---

## No modes, no depth dial

There is exactly one output: the complete meaningful knowledge of the video, as
the learner's notes, opening with the Quick Summary callout and the
`## Summary` bullets right after the metadata, then the full detailed
write-up below, then the fixed Ending Deep-Dive Layer (FIXED §7) at the very
end. Nothing is filtered by priority. A short video → short notes (the Ending
Deep-Dive Layer shrinks proportionally too — it never pads a thin video to
look thorough); a dense video → long notes. Length comes from the video, never
from a setting, and never padded to fill a structure.

Timestamps: optional and only at section level (e.g. "Lesson 3 — around 5:50"), for
jump-back — never one per point.

---

## Formatting devices — a menu, use only when earned

- **Code block + language tag** — any on-screen or dictated code, commands,
  config, terminal output.
- **Table** — the video weighs options / positions / before-vs-after.
- **`[!quote]` callout** — a creator's direct, memorable line.
- **`[!note]`/`[!tip]`/`[!warning]` callout** (see OBSIDIAN FORMAT above) — the
  1–3 load-bearing claims, a recommendation, or a limitation worth setting apart.
  Bold lead-in works too when a full callout is overkill.
- **Numbered list** — a real ordered process / steps / a video's own numbered points.
- **Mermaid diagram** — only where the structure is genuinely visual (architecture,
  workflow, hierarchy, a decision flow, a dependency graph). Build it **strictly
  from Canonical Knowledge** — invent no boxes or arrows. On `terminal` render it
  becomes a labelled text box; on `md`/`html` it draws.

If none of these fit the video, use plain headings and prose. That's a valid note.

---

## Bold — what earns it, everywhere including Summary

`**bold**` isn't just typography here — once the note goes through a real
renderer (this skill's own `render.py`, or `md_to_book.py` / any Obsidian-style
tool), bold text turns into a colorful highlighter-pen mark, not just heavier
type. So bold what's genuinely load-bearing, not everything that feels a
little important:

1. **Numbers/stats/money/dates worth remembering** — `$200`, `3-4 targets`,
   `~5-6 hours`, `95%`, `4 months`.
2. **The one named concept/technique/term** a sentence or bullet is actually
   about — on its first prominent mention in that unit.
3. **The key outcome/result** — what happened, what changed — as a short phrase,
   not the whole sentence.
4. **1–3 bold spans per sentence/bullet, never more.** Bolding everything reads
   as bolding nothing — and now that bold renders as a highlighter color, over-
   bolding turns a page into a rainbow wall instead of drawing the eye to what
   actually matters.

**This applies exactly as much to `## Summary` bullets as to body
paragraphs.** A bullet compressing several body sentences into one line still
carries whatever was load-bearing in them — a bullet with zero bold in a note
whose body bolds generously is a sign something got flattened, not simplified.
Check this explicitly in the Honesty-check pass (METHOD §5): skim the whole
Summary section alone — every bullet should have its own 1–3 bold
spans on its own key numbers, terms, or outcomes, not just the first bullet or
two.

---

## Worked example shells (illustrative only — DO NOT copy the shape)

These show the *range*. Your note's shape (below the Quick Summary + Detailed
Summary) comes from your video, not from here. Every shell still opens, right
after the metadata block, with the fixed Quick Summary callout and
`## Summary` — and every shell, not shown below for brevity, still
ends with the fixed Ending Deep-Dive Layer from FIXED §7
(`## What I Actually Learned` → `## Interview Q&A` → conditional
Code/Mind-Map/Formulas → `## Quick Revision`).

**A numbered-lesson talk** (video literally numbers its points):
```
<frontmatter>
<metadata block>
> [!abstract] Quick Summary
> <2-4 plain-prose lines: what this video is, what it covers>
## Summary
- <point>

- <point>
## <core idea running under everything, in the video's words>
## Lesson 1 — <video's own name for it>
## Lesson 2 — <…>
...
## <closing / "what actually changed" if the video has one>
```

**A debate / two-sides discussion:**
```
<frontmatter>
<metadata block>
> [!abstract] Quick Summary
> <2-4 plain-prose lines>
## Summary
- …
## <what's being argued and by whom>
## <Position A> — <name it as the speaker frames it>
## <Position B> — <…>
## Where they clash
## What's left unresolved
```

**A hands-on tutorial:**
```
<frontmatter>
<metadata block>
> [!abstract] Quick Summary
> <2-4 plain-prose lines>
## Summary
- …
## <what gets built / done, and the starting point assumed>
## Setup / what you need
## Steps  (numbered, with the gotchas the video flags inline)
## Final result — what you end up with
## Where the video warns you / common mistakes
```

**A single-topic explainer with no inherent structure:**
```
<frontmatter>
<metadata block>
> [!abstract] Quick Summary
> <2-4 plain-prose lines>
## Summary
- …
## <the one thing this video explains>
## <sub-concept 1, grouped by relationship>
## <sub-concept 2>
## <why it matters / where it's used, if the video says>
```
