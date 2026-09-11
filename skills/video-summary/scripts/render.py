#!/usr/bin/env python3
"""
render.py  —  take Claude's finished Hinglish summary (markdown) and emit it in
the requested output format. Presentation only; it never changes wording.

  --format terminal  (default): print to stdout for the chat/terminal. ```mermaid
                     blocks are shown as labeled text blocks (terminals can't draw).
  --format md      : write a .md file (mermaid left intact; renders on GitHub etc.)
  --format html    : write a self-contained .html with a clean dark theme and
                     Mermaid.js (via CDN) so diagrams render in a browser.

Usage: python3 render.py --in summary.md --format html [--out PATH]
"""
import sys, os, argparse, re, html as _html

def read(p): return open(p, encoding="utf-8").read()

def _split_row(line):
    """Table row -> cells, splitting on unescaped '|' only (a literal pipe in a
    cell -- e.g. a "Title | Subtitle" style video title -- is written as \\|)."""
    cells = re.split(r"(?<!\\)\|", line.strip().strip("|"))
    return [c.strip().replace("\\|", "|") for c in cells]

# list-marker strippers, precompiled so no backslash lands inside an f-string
# (that is a SyntaxError on Python < 3.12)
_UL_STRIP = re.compile(r"^\s*[-*]\s+")
_OL_STRIP = re.compile(r"^\s*\d+\.\s+")

# YAML frontmatter block, if present -- Obsidian-vault metadata, not meant for
# display in chat/html (the note's own metadata block right under the H1
# already carries the human-readable version).
_FRONTMATTER = re.compile(r"^---\n.*?\n---\n?", re.S)

# Obsidian callouts: "> [!type] optional title" then more "> "-prefixed lines.
_CALLOUT_START = re.compile(r"^>\s*\[!(\w+)\][-+]?\s*(.*)$")
_QUOTE_LINE = re.compile(r"^>\s?(.*)$")
_CALLOUT_LABEL = {
    "note": "Note", "abstract": "Summary", "summary": "Summary", "tldr": "TL;DR",
    "info": "Info", "todo": "To-do", "tip": "Tip", "hint": "Tip", "important": "Important",
    "success": "Success", "check": "Success", "done": "Done",
    "question": "Question", "help": "Help", "faq": "FAQ",
    "warning": "Warning", "caution": "Caution", "attention": "Attention",
    "failure": "Failure", "fail": "Failure", "missing": "Missing",
    "danger": "Danger", "error": "Error", "bug": "Bug",
    "example": "Example", "quote": "Quote", "cite": "Quote",
}

def split_frontmatter(md):
    """Returns (frontmatter_block_or_'', rest_of_markdown)."""
    m = _FRONTMATTER.match(md)
    return (m.group(0), md[m.end():]) if m else ("", md)

# ---- terminal ----
def to_terminal(md):
    _, md = split_frontmatter(md)  # Obsidian metadata, not chat-relevant
    def repl(m):
        return "\n┌─ diagram (mermaid) " + "─"*40 + "\n" + \
               "\n".join("│ " + ln for ln in m.group(1).strip().splitlines()) + \
               "\n└" + "─"*59 + "\n"
    return re.sub(r"```mermaid\n(.*?)```", repl, md, flags=re.S)

# ---- minimal, dependency-free markdown -> html ----
def to_html_body(md):
    # pull mermaid blocks out first
    mer = []
    def stash(m):
        mer.append(m.group(1)); return f"@@MERMAID{len(mer)-1}@@"
    md = re.sub(r"```mermaid\n(.*?)```", stash, md, flags=re.S)
    # other fenced code
    code = []
    def stashc(m):
        code.append(m.group(1)); return f"@@CODE{len(code)-1}@@"
    md = re.sub(r"```[a-zA-Z0-9]*\n(.*?)```", stashc, md, flags=re.S)

    def inline(t):
        t = _html.escape(t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<em>\1</em>", t)
        t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
        t = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', t)
        return t

    out, lines, i = [], md.split("\n"), 0
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1; continue
        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m:
            lv = len(m.group(1)); out.append(f"<h{lv}>{inline(m.group(2))}</h{lv}>"); i += 1; continue
        if _UL_STRIP.match(ln):
            items = []
            while i < len(lines) and _UL_STRIP.match(lines[i]):
                li = inline(_UL_STRIP.sub("", lines[i]))
                items.append(f"<li>{li}</li>"); i += 1
            out.append("<ul>" + "".join(items) + "</ul>"); continue
        if _OL_STRIP.match(ln):
            items = []
            while i < len(lines) and _OL_STRIP.match(lines[i]):
                li = inline(_OL_STRIP.sub("", lines[i]))
                items.append(f"<li>{li}</li>"); i += 1
            out.append("<ol>" + "".join(items) + "</ol>"); continue
        if ln.strip().startswith("|") and i+1 < len(lines) and re.match(r"^\s*\|[-:\s|]+\|\s*$", lines[i+1]):
            head = _split_row(ln)
            i += 2; rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(_split_row(lines[i])); i += 1
            th = "".join(f"<th>{inline(c)}</th>" for c in head)
            trs = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows)
            out.append(f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"); continue
        if ln.strip() == "---":
            out.append("<hr>"); i += 1; continue
        cm = _CALLOUT_START.match(ln)
        if cm:
            ctype = cm.group(1).lower()
            title = cm.group(2).strip() or _CALLOUT_LABEL.get(ctype, ctype.capitalize())
            body_lines = []; i += 1
            while i < len(lines) and _QUOTE_LINE.match(lines[i]) and not _CALLOUT_START.match(lines[i]):
                body_lines.append(_QUOTE_LINE.match(lines[i]).group(1)); i += 1
            inner = to_html_body("\n".join(body_lines)) if body_lines else ""
            out.append(f'<div class="callout" data-callout="{ctype}">'
                       f'<div class="callout-title">{inline(title)}</div>'
                       f'<div class="callout-body">{inner}</div></div>')
            continue
        if ln.strip().startswith(">"):
            q_lines = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                qm = _QUOTE_LINE.match(lines[i])
                q_lines.append(qm.group(1) if qm else lines[i].lstrip(">").strip())
                i += 1
            out.append("<blockquote>" + to_html_body("\n".join(q_lines)) + "</blockquote>")
            continue
        para = [ln]; i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,6}\s|[-*]\s|\d+\.\s|\|)", lines[i]):
            para.append(lines[i]); i += 1
        out.append("<p>" + inline(" ".join(para)) + "</p>")

    body = "\n".join(out)
    for j, c in enumerate(code):
        body = body.replace(f"@@CODE{j}@@", f"<pre><code>{_html.escape(c)}</code></pre>")
    for j, m in enumerate(mer):
        body = body.replace(f"@@MERMAID{j}@@", f'<div class="mermaid">{_html.escape(m)}</div>')
    return body

HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>document.addEventListener("DOMContentLoaded",()=>mermaid.initialize({{startOnLoad:true,theme:"dark"}}));</script>
<style>
  :root{{--bg:#0f1115;--fg:#e6e6e6;--mut:#9aa4b2;--acc:#7aa2f7;--card:#171a21;--bd:#252a34}}
  *{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--fg);
    font:16px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}}
  .wrap{{max-width:820px;margin:0 auto;padding:48px 24px 96px}}
  h1{{font-size:1.9rem;line-height:1.25;margin:.2em 0 .6em}} h2{{margin-top:2em;
    border-bottom:1px solid var(--bd);padding-bottom:.3em}} h3{{margin-top:1.6em;color:var(--acc)}}
  a{{color:var(--acc)}} hr{{border:none;border-top:1px solid var(--bd);margin:2em 0}}
  code{{background:var(--card);padding:.1em .35em;border-radius:4px;font-size:.9em}}
  pre{{background:var(--card);border:1px solid var(--bd);border-radius:8px;padding:14px;overflow:auto}}
  pre code{{background:none;padding:0}}
  table{{border-collapse:collapse;width:100%;margin:1em 0}} th,td{{border:1px solid var(--bd);
    padding:8px 10px;text-align:left}} th{{background:var(--card)}}
  ul,ol{{padding-left:1.4em}} li{{margin:.3em 0}}
  .mermaid{{background:var(--card);border:1px solid var(--bd);border-radius:8px;padding:16px;margin:1.2em 0;text-align:center}}
  blockquote{{margin:1em 0;padding:.2em 1em;border-left:4px solid var(--bd);color:var(--mut)}}
  .callout{{margin:1em 0;padding:10px 14px;border-radius:6px;background:var(--card);
    border-left:4px solid var(--acc)}}
  .callout-title{{font-weight:600;margin-bottom:.3em}}
  .callout-body p:first-child{{margin-top:0}} .callout-body p:last-child{{margin-bottom:0}}
  .callout[data-callout="warning"],.callout[data-callout="caution"],.callout[data-callout="attention"]{{border-color:#e0af02}}
  .callout[data-callout="danger"],.callout[data-callout="error"],.callout[data-callout="bug"],
  .callout[data-callout="failure"],.callout[data-callout="fail"],.callout[data-callout="missing"]{{border-color:#e5484d}}
  .callout[data-callout="tip"],.callout[data-callout="hint"],.callout[data-callout="important"],
  .callout[data-callout="success"],.callout[data-callout="check"],.callout[data-callout="done"]{{border-color:#3fb950}}
  .callout[data-callout="question"],.callout[data-callout="help"],.callout[data-callout="faq"]{{border-color:#a371f7}}
  .callout[data-callout="example"]{{border-color:#9aa4b2}}
  .callout[data-callout="quote"],.callout[data-callout="cite"]{{border-color:#9aa4b2;font-style:italic}}
  .foot{{color:var(--mut);font-size:.85rem;margin-top:3em;border-top:1px solid var(--bd);padding-top:1em}}
</style></head><body><div class="wrap">
{body}
<div class="foot">video-summary • Canonical Knowledge se generate kiya gaya</div>
</div></body></html>"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--mode", default=None, help=argparse.SUPPRESS)  # accepted, ignored
    ap.add_argument("--format", default="terminal", choices=["terminal", "md", "html"])
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    md = read(a.inp)

    if a.format == "terminal":
        print(to_terminal(md)); return
    if a.format == "md":
        out = a.out or "summary.md"
        open(out, "w", encoding="utf-8").write(md)  # frontmatter kept -- this IS the vault file
        print(f"[render] wrote {out}"); return
    # html
    _, body_md = split_frontmatter(md)  # Obsidian metadata isn't meant for on-page display
    m = re.search(r"^#\s+(.*)$", body_md, re.M)
    title = m.group(1) if m else "Video Summary"
    out = a.out or "summary.html"
    open(out, "w", encoding="utf-8").write(
        HTML.format(title=_html.escape(title), body=to_html_body(body_md)))
    print(f"[render] wrote {out}")

if __name__ == "__main__":
    main()
