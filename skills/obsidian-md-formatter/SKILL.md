---
name: obsidian-md-formatter
description: Formats any content — explanations, notes, code snippets, vulnerability writeups, research summaries — into Obsidian-flavored Markdown matching a personal Obsidian vault's conventions (YAML frontmatter, headings, callouts, wiki-links, embeds, tables, footnotes, tags, Mermaid diagrams, math/LaTeX, Dataview queries). Always consult this skill before writing or saving any .md / markdown file. Trigger on requests like "save this to md", "save this as a note", "notes bana do" (Hinglish for "make notes"), "write it in Obsidian format", or any request to turn an explanation, summary, or code into a note — even if the word "obsidian" is never said. The output must be ready to drop straight into an Obsidian vault with zero reformatting needed.
---

# Obsidian Markdown Formatter

## Why this skill exists

Vaults built on Obsidian conventions (wiki-links, callouts, Dataview, frontmatter)
are usually maintained without opening the Obsidian app to hand-format every note.
That means: whenever any `.md` content gets written (an explanation, a vulnerability
writeup, a code snippet), it needs to be Obsidian-ready the first time. If it has to
be reformatted later, the whole point is defeated — so these rules apply consistently
to every markdown file, even the smallest one.

## When to trigger

- "save this to md" / "save this as a note" / "make me some notes"
- "write this in Obsidian format"
- Any explanation, summary, research, or code being saved as a note — even if the
  word "obsidian" never comes up
- Any `.md` file being created or edited

## Core workflow

1. **Understand the content** — is it a concept explanation, a vulnerability writeup,
   a code snippet, a comparison, or a research summary?
2. **Add frontmatter** — at the top of every note (template below).
3. **Choose the structure** — use the right feature for the content type (decision
   table below).
4. **Follow the quick syntax** — this file's common patterns.
5. **Check the deep reference** — if the quick cheatsheet doesn't cover it (a rare
   callout type, a specific Mermaid diagram, a Dataview query, complex math), open
   `references/syntax-reference.md` — it has the full detail with a table of contents.
6. **Validate** — run through the checklist below before finalizing.

## Frontmatter — always at the top of every note

```yaml
---
title: <note title>
date: <YYYY-MM-DD>
tags: [relevant, tags, here]
aliases: []
---
```

If the content is a specific type (e.g. vulnerability, tool-note, concept-note), an
extra `type:` field can be added (`type: vulnerability`). This is purely
context-dependent, not a fixed rule.

## Formatting decision guide

| Content type | Obsidian feature to use |
|---|---|
| Warning, risk, critical info | Callout `[!warning]` or `[!danger]` |
| Tip, best practice | Callout `[!tip]` |
| Definition, summary | Callout `[!note]` or `[!abstract]` |
| Step-by-step process (linear) | Ordered list |
| Step-by-step process (branching/decision points) | Mermaid flowchart |
| Comparing two or more things | Table |
| Reference to another note/topic | Wiki-link `[[Note Name]]` |
| Citation of an external source | Footnote `[^1]` |
| Code, command, payload | Fenced code block **with language tag** |
| Formula, calculation | Math/LaTeX — inline `$...$`, block `$$...$$` |
| Attack flow, architecture, sequence, state changes | Mermaid diagram (correct type in the reference file) |
| Categorization / searchability | Tags — inline `#tag` or frontmatter `tags:` |
| Structured, queryable metadata | Dataview-compatible frontmatter properties |

## Quick syntax cheatsheet (most-used)

**Headings** — exactly one H1, then properly nested H2/H3:
```markdown
# Note Title
## Section
### Sub-section
```

**Text formatting:**
```markdown
**bold**   *italic*   ***bold italic***   ~~strikethrough~~   `inline code`
```

**Lists:**
```markdown
- Point one
  - Nested point
- [ ] Incomplete task
- [x] Completed task

1. Step one
2. Step two
```

**Code block (a language tag is required):**
````markdown
```python
def example():
    pass
```
````

**Table:**
```markdown
| Header 1 | Header 2 |
|----------|----------|
| Value    | Value    |
```

**Wiki-link:**
```markdown
[[Note Name]]
[[Note Name|Display Text]]
[[Note Name#Heading]]
```

**Callout:**
```markdown
> [!warning] Custom title (optional)
> The callout's content goes here
```

**Math:**
```markdown
Inline: $E = mc^2$

Block:
$$
E = mc^2
$$
```

**Footnote:**
```markdown
This is a claim[^1]

[^1]: Source or explanation
```

**Tag:**
```markdown
#appsec #owasp-top-10
```

## Validation checklist (before finalizing)

- [ ] YAML frontmatter is present (title, date, tags minimum)
- [ ] Exactly one H1, every other heading properly nested (H3 under H2, etc.)
- [ ] Wiki-links `[[ ]]` used only for genuine cross-references — don't turn random
      words into links
- [ ] Every code block has a language tag (payloads/commands too)
- [ ] Callout type is valid (from the reference file's list)
- [ ] Mermaid diagram used only when the flow is genuinely multi-step/branching —
      not overkill for a simple 2-3 line thing
- [ ] No excluded syntax (see below) has leaked into the note content

## Out of scope for this skill

These are part of the general Obsidian cheatsheet but irrelevant to note *content*
formatting — so they're consciously excluded: keyboard shortcuts, the community
plugin list, best-practices/file-organization tips, performance tips, export
options, troubleshooting steps, vault structure examples, the Obsidian URI scheme,
Publish settings, search syntax, Templater/QuickAdd automation, Canvas/Excalidraw
file formats.

## Full reference

`references/syntax-reference.md` has everything in detail — every callout type
(aliases included), every Mermaid diagram type, Dataview query variations, complex
math examples, embed syntax (image/PDF/audio/video/block), block IDs, comments,
aliases. Check there whenever the quick cheatsheet doesn't have the answer.
