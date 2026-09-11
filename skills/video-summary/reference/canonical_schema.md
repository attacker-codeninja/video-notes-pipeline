# Canonical Knowledge — schema (what Claude reads/writes)

Canonical Knowledge is the single source of truth. You never write `canonical.json`
by hand — you emit a **delta** per part and `state.py merge` folds it in. This file
is the contract for those deltas and for the reconcile ops.

All human-readable text fields (`meaning`, `statement`, `describes`, notes) are in
**clear English**, always — regardless of the video's language.

## Per-part delta  (you write `delta_<N>.json`, then `state.py merge`)

```json
{
  "part": 0,

  "concepts": [
    {
      "id": "c_recon",                 // stable slug you choose; REUSE the id from the
                                       //   context package's active_concepts to CONTINUE a concept
      "name": "Reconnaissance",
      "type": "concept|entity|method|tool|event|process",
      "meaning": "<English — what it is, in the video's context>",
      "status": "introduced|developing|established|refined|corrected|uncertain|disputed",
      "priority": "P0|P1|P2|P3",       // your first-pass importance (see rubrics.md)
      "aliases": ["recon"],
      "evidence": [                    // reference only, never copy transcript text
        {"t_start": 120.0, "t_end": 145.0, "source": "transcript|frame|ocr|audio",
         "frame": "frames/frame_0041.jpg"}   // frame only when source is frame/ocr
      ]
    }
  ],

  "claims": [
    {
      "id": "cl_paidbug",
      "statement": "<English — what is being claimed>",
      "claim_type": "factual|creator_opinion|interpretation|recommendation|hypothesis|prediction|reported",
      "source": "creator|guest|cited_source",
      "confidence": "stated|hedged|speculative",
      "scope": "<condition/when it applies, if any>",
      "evidence": [{"t_start": 300.0, "t_end": 312.0, "source": "transcript"}],
      "supports": ["c_recon"],         // concept ids this claim backs
      "qualification": "<important limit/exception, if any>"
    }
  ],

  "relationships": [
    {"from": "c_recon", "to": "c_bugs", "type": "leads_to"}
    // types: depends_on explained_by supported_by contradicted_by qualified_by
    //        leads_to answered_by related_to participates_in corrected_by
    //        refers_to illustrates causes supports explains introduced_in continued_in
  ],

  "pending_threads": [
    {"id": "pt_heavyload", "question": "<English>", "status": "introduced|developing|resolved|unresolved_at_end"}
  ],

  "uncertainty": [
    {"ref": "cl_paidbug", "level": "known|likely|uncertain|unknown", "why": "<English reason>"}
  ],

  "visual_knowledge": [
    {"t": 512.0, "frame": "frames/frame_0130.jpg",
     "describes": "<English — what the slide/diagram/on-screen code actually shows>",
     "node": "c_recon"}               // node this visual belongs to (optional)
  ],

  "coverage_note": "<English — one line: what this part covered>"
}
```

### Rules the merge relies on
- **Continue, don't duplicate.** A concept spanning parts keeps ONE id across all its
  parts. Reuse the id shown in `active_concepts`. New id only for genuinely new concepts.
- **Status never regresses** on merge (introduced → developing → established → …).
- **Evidence is references only** — timestamps + source + optional frame. Never paste
  transcript sentences into the store.
- **Don't invent.** If the part evidence doesn't support a field, leave it out. Missing
  ≠ made up.

## Reconcile ops  (you write `reconcile.json`, then `state.py reconcile`)

```json
{ "ops": [
  {"op":"merge","from":"c_dup","into":"c_recon"},           // same concept, two ids -> one
  {"op":"split","id":"c_mixed","into":[ {full concept}, {full concept} ]},
  {"op":"set_status","id":"c_recon","status":"corrected"},
  {"op":"set_priority","id":"c_recon","priority":"P0"},
  {"op":"resolve_thread","id":"pt_heavyload","status":"resolved","note":"<English>"},
  {"op":"add_relationship","from":"cl_a","to":"cl_b","type":"corrected_by"}
]}
```

`state.py` also computes, on every merge/reconcile: `_centrality` (in-degree over
importance edges) and `priority_effective` (a high-centrality node is promoted one
tier). You don't set those.
