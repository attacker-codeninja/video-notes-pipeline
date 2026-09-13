# Rubrics — the judgment rules (used at understanding, reconcile, select, validate)

These encode the decisions the architecture left "conceptual". They are the same
rules everywhere, so two runs don't disagree on what matters.

## 1. What counts as "meaningful" (the one definition, used everywhere)

Content is **meaningful** if removing it would change the viewer's understanding of:
the subject, a claim, a conclusion, a dependency, a process, or an important
qualification. If removing it changes nothing, it is **not** meaningful — it's filler,
repetition, or chit-chat, and it does not become a node.

- Filler / greetings / "like & subscribe" / sponsor reads → drop, never a node.
- The SAME point said twice → one node; keep the most informative wording as `meaning`.
- Repetition that ADDS something new (a new condition, a better example) → NOT redundant;
  capture the new part.
- Compress information, never meaning. `A → causes → B → enables → C` must survive as a
  chain, never flatten to "A, B, C are related".

## 2. Triangulation (Layer 1 already gives you 3 sources — use them)

Every concrete claim (a number, name, command, price, URL, technical term) must be
resolved BEFORE it enters the store. Per segment you have:
- `text` = source A (auto_caption / primary reading)
- `indep_text` + `indep_match` = source B (independent Whisper) and whether it agrees
- `ocr_text` / `ocr_supports` / `frame` = source C (on-screen text) when present
- `vad` = voice-activity check (flags "speech" that wasn't actually spoken)
- `flag` = true when the spoken reading is suspect (`indep_disagree`, `vad_no_speech`, `vad_low`)

Rules:
- A and B agree → trust the spoken content, use it.
- A and B disagree (`flag` true) → **Read the frame(s) at that timestamp**; on-screen
  text is the tiebreaker for anything visible. Frame paths are in the context package
  (`part_evidence.frames[].abs`).
- Frame contradicts the narration → the frame wins for the visual claim (speaker can
  misspeak; slide is ground truth).
- Nothing resolves it → do NOT pick a version. Record the node with `uncertainty`
  (`level: uncertain`) and soften the `meaning` ("the video says something like X here,
  exact wording unclear"). Never assert a guessed value as fact.
- Every source silent on a detail → leave it out entirely. A gap is not a licence to fill.

Frame-reading is **selective, not all-318**: read frames (a) at part boundaries for
orientation, (b) at any `flag`ged segment carrying a concrete claim, (c) where on-screen
text plausibly carries knowledge (code, slides, terminal, diagrams). That is the cost of
accuracy; sampling "representative" frames when a specific claim needs checking is not OK.

## 3. Importance priority (P0–P3) — set on each node at understanding time

- **P0 Essential** — central subject; main claims; final conclusions; critical
  dependencies; essential mechanisms; critical corrections/contradictions.
- **P1 Important** — important explanations; strong supporting evidence; meaningful
  examples; important relationships; relevant qualifications.
- **P2 Supporting** — secondary examples; extra context; minor but useful detail.
- **P3 Optional** — low-value detail, leftover repetition, redundant conversational bits.

`state.py` then promotes any node with high centrality (≥2 importance-edges pointing in)
by one tier automatically — so a concept many things depend on rises even if you first
marked it P1.

Priority is **not** a presentation filter. There is one output and it carries **all
meaningful nodes** (P0–P3). `priority_effective` only guides the write-up: P0 leads and
gets room, P3 gets a line — nothing meaningful is dropped. On a very long video, priority
still governs *compression* (see §7): low-priority stable nodes get shortened, never cut.

## 4. Concept identity — merge / split (never by name alone)

- **Do NOT merge two concepts just because names are similar.** Merge only when meaning +
  evidence show they are the same thing. When they are, use one `merge` op.
- **Split** when one id turns out to cover two distinct things — emit `split` with full
  replacement nodes.
- Continuity across parts is handled by reusing ids during understanding; the reconcile
  step is the safety net for accidental duplicates you spot at the end.

## 5. Pending threads vs uncertainty (keep separate)

- **Pending thread** = a question/reasoning the video opened. If never answered →
  `unresolved_at_end`. Do NOT invent an answer; the summary says the video leaves it open.
- **Uncertainty** = limited confidence in a piece of knowledge (bad transcript, hedged
  speaker, unconfirmed visual). Record level + why. Do not hide a real contradiction by
  calling it "uncertainty" — a contradiction gets `contradicted_by` / `qualified_by`
  edges and, once resolved, a scoped final statement.

## 6. Contradiction handling

Earlier "A is always better", later "B is better when load is large" → do not erase the
first. Reconcile to the final scoped position: broad claim → later qualification → final
understanding with the qualification attached. The summary states the final scoped view.

Opinion stays opinion. "Creator argues X" must never become "X is true". Preserve
`claim_type` and `source` into the wording ("the creator believes…", "in the creator's
view…").

## 7. Failure / degradation (never fabricate to fill a gap)

- Transcript gap / all sources silent → smaller/omitted node + coverage note; no guess.
- Low-confidence unresolved → node with `uncertainty: uncertain`.
- State getting large on a long video → compress STABLE nodes (merge overlapping,
  shorten `meaning`) but keep every P0 intact, all distinctions, causal chains,
  qualifications, contradictions, pending threads. Archived ≠ deleted.

## 8. Summary validation (after generation, before showing)

Re-read your generated notes against `state.py select` output and check:
- Coverage — every meaningful node (P0–P3) is represented somewhere in the notes, and
  the `## Summary` bullets (near the top) miss nothing meaningful that the
  detailed sections below go on to cover.
- Summary format — `## Summary` is a bulleted list with one blank line between
  consecutive bullets, and **every bullet carries its own 1–3 bold spans** on
  its load-bearing numbers/terms/outcomes (`templates.md` → "Bold —
  what earns it") — not just the first bullet or two while the rest go flat.
- Ending Deep-Dive Layer — `## What I Actually Learned`, `## Interview Q&A`, and
  `## Quick Revision` are present (conditional `## Code Walkthrough`/`## Mind Map`/
  `## Formulas` only where earned), in that fixed order, at the very end of the note.
- Accuracy — every concrete claim maps to a node; nothing invented; no node contradicted.
- Faithfulness — opinions stay opinions; scopes/qualifications intact.
- Uncertainty — hedged/unresolved things are still hedged/open in the notes.
Fail on any → fix that section and re-check. **Bounded scope:** this checks fidelity to
Canonical Knowledge, NOT truth-vs-reality (that blind spot is why `evidence` timestamps
are kept — so a human can spot-check the source).
