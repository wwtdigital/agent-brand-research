#!/usr/bin/env python3
"""
fix_lists.py — One-shot post-processor for existing A/B HTML (HyperText Markup Language) reports.

Finds literal `1.  ` and `*   ` patterns inside table cells that weren't
converted to proper HTML lists, and replaces them with <ol>/<ul> markup.

Usage:
    python fix_lists.py                  # fixes the most recent ab_report_*.html
    python fix_lists.py ab_report_X.html # fixes a specific file
"""

import re
import sys
import glob
from pathlib import Path


def inline_fmt(text: str) -> str:
    """Bold, italic, inline code."""
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*",     r"<em>\1</em>",          text)
    text = re.sub(r"`(.+?)`",        r"<code>\1</code>",      text)
    return text


def fix_cell(content: str) -> str:
    """
    Walk through the HTML (HyperText Markup Language) content of a single <td> cell line by line.
    Convert any unprocessed Markdown (formatted text) list syntax into proper <ol>/<ul> tags.
    Leaves already-converted HTML tags untouched.
    """
    lines = content.split("\n")
    out = []
    list_state = None  # None | 'ul' | 'ol'

    def close_list():
        nonlocal list_state
        if list_state:
            out.append(f"</{list_state}>")
            list_state = None

    def open_list(kind):
        nonlocal list_state
        if list_state != kind:
            close_list()
            out.append(f"<{kind}>")
            list_state = kind

    for line in lines:
        stripped = line.strip()

        # Numbered list item: "1.  text", "2.  text", etc.
        # The text portion may already contain <strong> tags — leave them as-is.
        m_num = re.match(r"^\s*\d+\.\s+(.+)$", stripped)
        if m_num:
            item = m_num.group(1).strip()
            # Only apply inline formatting if the item has no HTML tags yet
            if not re.search(r"<[a-z]", item):
                item = inline_fmt(item)
            open_list("ol")
            out.append(f"<li>{item}</li>")
            continue

        # Bullet item: "*   text", "-   text", with any amount of whitespace
        m_bul = re.match(r"^\s*[\*\-]\s+(.+)$", stripped)
        if m_bul:
            item = m_bul.group(1).strip()
            if not re.search(r"<[a-z]", item):
                item = inline_fmt(item)
            open_list("ul")
            out.append(f"<li>{item}</li>")
            continue

        # Any non-list line closes an open list
        close_list()
        out.append(line)

    close_list()
    return "\n".join(out)


def fix_html(html: str) -> str:
    """Apply fix_cell() to every <td> element in the document."""
    def replace_td(m):
        attrs   = m.group(1)   # e.g., ' class="col-a"'
        content = m.group(2)
        return f"<td{attrs}>{fix_cell(content)}</td>"

    return re.sub(r"<td([^>]*)>(.*?)</td>", replace_td, html, flags=re.DOTALL)


def main():
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
    else:
        candidates = sorted(glob.glob(
            str(Path(__file__).parent / "ab_report_*.html")
        ))
        if not candidates:
            print("No ab_report_*.html files found in this directory.")
            sys.exit(1)
        target = Path(candidates[-1])

    if not target.exists():
        print(f"File not found: {target}")
        sys.exit(1)

    print(f"Processing: {target.name}")
    original = target.read_text(encoding="utf-8")
    fixed    = fix_html(original)
    target.write_text(fixed, encoding="utf-8")
    print(f"Done. Lists updated in: {target.name}")


if __name__ == "__main__":
    main()
