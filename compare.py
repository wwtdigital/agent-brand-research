#!/usr/bin/env python3
"""
Ascension Clinical Agent — A/B System Prompt Comparison
========================================================
Runs a set of test queries through Gemini twice per query:
  A) No system prompt (baseline Gemini behavior)
  B) With the Ascension clinical system prompt

Prints a side-by-side terminal comparison and saves a full
Markdown report for sharing or archiving.

Requirements
------------
    pip install google-generativeai

Setup
-----
    1. Get a free API (Application Programming Interface) key at https://aistudio.google.com/app/apikey
    2. Export it:  export GEMINI_API_KEY="your-key-here"
    3. Run:        python compare.py

    Optional — override the model:
        MODEL=gemini-1.5-pro python compare.py
"""

import os
import sys
import time
import textwrap
from pathlib import Path
from datetime import datetime

try:
    import google.generativeai as genai
except ImportError:
    print("\n  Missing dependency. Run:  pip install google-generativeai\n")
    sys.exit(1)


# ── Configuration ──────────────────────────────────────────────────────────────

# Model to use. gemini-2.0-flash is fast and free-tier friendly.
# Swap to gemini-1.5-pro for higher quality output if you have quota.
MODEL = os.environ.get("MODEL", "gemini-2.5-flash")

# Paste your API (Application Programming Interface) key here:
os.environ["GEMINI_API_KEY"] = "AIzaSyBWpHlDd9xYwpDe4tfc2R18CDjlfYobPOA"

# Path to the system prompt file (relative to this script)
SYSTEM_PROMPT_FILE = Path(__file__).parent / "system_prompt.md"

# Output report filename (timestamped so runs don't overwrite each other)
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_FILE = Path(__file__).parent / f"ab_report_{TIMESTAMP}.html"

# Seconds to wait between API (Application Programming Interface) calls — keeps free-tier rate limits happy
REQUEST_DELAY = 1.0


# ── Test Queries ───────────────────────────────────────────────────────────────
#
# Organized by category. Add, remove, or edit queries to match the scenarios
# most relevant to your rollout. Each string is sent verbatim to both models.

TEST_QUERIES = [

    # --- Policy & Procedure Q&A (Question and Answer) ---
    "What is the required process for two-nurse verification before administering a high-alert medication?",
    "How often are associates required to complete hand hygiene competency training?",
    "What should a caregiver do when a patient refuses a recommended treatment?",
    "What is the escalation path if a caregiver suspects a colleague is impaired on shift?",

    # --- Clinical Data & Metrics ---
    "What was our CLABSI (Central Line-Associated Bloodstream Infection) rate last quarter and how does it compare to the national benchmark?",
    "Show me fall prevention metrics for the past year and highlight any trends.",
    "Our HCAHPS (Hospital Consumer Assessment of Healthcare Providers and Systems) scores dropped two points this quarter. What does that typically mean and what should we be looking at?",

    # --- Patient Safety ---
    "A caregiver believes they made a medication error. What steps should they take right now?",
    "What is Ascension's Healing without Harm program and how does it relate to daily care delivery?",

    # --- Identity & Scope ---
    "Who are you and what can you help me with?",
    "Can you recommend the best treatment protocol for a patient presenting with early-stage sepsis?",
    "Can you pull up a patient's chart for me?",

    # --- Vocabulary & Tone Edge Cases ---
    # These are designed to expose whether the system prompt correctly
    # redirects language (e.g., 'employees' → 'associates').
    "As an employee, I need to know the policy on employee scheduling during holidays.",
    "What does your company's zero-harm initiative actually require of staff on the floor?",
]


# ── Terminal Colors ────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"


# ── Helpers ────────────────────────────────────────────────────────────────────

def hr(char="─", width=82):
    print(char * width)

def wrap(text: str, width=78, indent="    ") -> str:
    """Wrap text preserving paragraph breaks."""
    paragraphs = text.splitlines()
    wrapped = []
    for para in paragraphs:
        if para.strip() == "":
            wrapped.append("")
        else:
            wrapped.extend(
                textwrap.wrap(para, width=width,
                              initial_indent=indent,
                              subsequent_indent=indent)
            )
    return "\n".join(wrapped)

def load_system_prompt(path: Path) -> str:
    """
    Reads system_prompt.md and strips the developer header block
    (everything up to and including the first '---' divider), returning
    only the instruction content suitable for API injection.
    """
    content = path.read_text(encoding="utf-8")
    parts = content.split("---", 1)
    return parts[1].strip() if len(parts) > 1 else content.strip()

def call_gemini(model, query: str) -> str:
    """Send a single query to a GenerativeModel instance."""
    try:
        response = model.generate_content(query)
        return response.text.strip()
    except Exception as exc:
        return f"[Request failed: {exc}]"

def print_result(index: int, total: int, query: str,
                 response_a: str, response_b: str) -> None:
    """Pretty-print one query's A/B results to the terminal."""
    print()
    hr("═")
    print(f"{BOLD}  Query {index + 1} of {total}{RESET}")
    hr()
    print(f"  {BOLD}{query}{RESET}\n")

    print(f"{CYAN}{BOLD}  ── A: Without system prompt ──────────────────────────────────────{RESET}")
    print(wrap(response_a))
    print()

    print(f"{GREEN}{BOLD}  ── B: With system prompt ─────────────────────────────────────────{RESET}")
    print(wrap(response_b))
    print()

def inline_fmt(text: str) -> str:
    """Apply bold, italic, and inline code formatting to a text fragment."""
    import re
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*",     r"<em>\1</em>",          text)
    text = re.sub(r"`(.+?)`",        r"<code>\1</code>",      text)
    return text

def md_to_html(text: str) -> str:
    """
    Lightweight Markdown (formatted text) → HTML (HyperText Markup Language) converter for the response cells.
    Handles bold, italic, inline code, headings, bullet lists (* or -),
    numbered lists (1. 2. 3.), and paragraph breaks — no external library needed.
    """
    import re
    lines = text.splitlines()
    html_lines = []
    list_state = None  # None | 'ul' | 'ol'

    def close_list():
        nonlocal list_state
        if list_state:
            html_lines.append(f"</{list_state}>")
            list_state = None

    def open_list(kind):
        nonlocal list_state
        if list_state != kind:
            close_list()
            html_lines.append(f"<{kind}>")
            list_state = kind

    for line in lines:
        stripped = line.strip()

        # ── Headings ──────────────────────────────────────────────────────────
        if stripped.startswith("### "):
            close_list()
            html_lines.append(f"<h4>{inline_fmt(stripped[4:])}</h4>")
            continue
        if stripped.startswith("## "):
            close_list()
            html_lines.append(f"<h3>{inline_fmt(stripped[3:])}</h3>")
            continue
        if stripped.startswith("# "):
            close_list()
            html_lines.append(f"<h2>{inline_fmt(stripped[2:])}</h2>")
            continue

        # ── Numbered list: "1." / "2." / "10." with any whitespace after ─────
        m_num = re.match(r"^\s*\d+\.\s+(.+)$", line)
        if m_num:
            open_list("ol")
            html_lines.append(f"<li>{inline_fmt(m_num.group(1).strip())}</li>")
            continue

        # ── Bullet list: "* " / "- " / "*   " with any whitespace after ──────
        m_bul = re.match(r"^\s*[\*\-]\s+(.+)$", line)
        if m_bul:
            open_list("ul")
            html_lines.append(f"<li>{inline_fmt(m_bul.group(1).strip())}</li>")
            continue

        # ── Blank line → close any open list, then paragraph break ───────────
        if stripped == "":
            close_list()
            html_lines.append("<br>")
            continue

        # ── Plain text line ───────────────────────────────────────────────────
        close_list()
        html_lines.append(inline_fmt(line))

    close_list()
    return "\n".join(html_lines)


def build_html_report(results: list, model: str) -> str:
    """Render all results as a self-contained HTML (HyperText Markup Language) comparison table."""
    generated = datetime.now().strftime("%B %d, %Y at %H:%M")
    total = len(results)

    rows = []
    for i, r in enumerate(results):
        query_html = r["query"].replace("<", "&lt;").replace(">", "&gt;")
        without_html = md_to_html(r["without"])
        with_html    = md_to_html(r["with"])
        rows.append(f"""
        <tr class="query-row">
            <td colspan="2">
                <span class="query-num">Query {i + 1} of {total}</span>
                {query_html}
            </td>
        </tr>
        <tr class="response-row">
            <td class="col-a">{without_html}</td>
            <td class="col-b">{with_html}</td>
        </tr>""")

    rows_html = "".join(rows)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ascension Clinical Agent — A/B Comparison Report</title>
    <style>
        *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 14px;
            line-height: 1.6;
            color: #1a1a1a;
            background: #f5f5f5;
            padding: 32px 24px;
        }}

        .report-header {{
            max-width: 1400px;
            margin: 0 auto 28px;
        }}

        .report-header h1 {{
            font-size: 22px;
            font-weight: 700;
            color: #0a2240;
            margin-bottom: 8px;
        }}

        .meta {{
            font-size: 13px;
            color: #555;
            display: flex;
            gap: 24px;
            flex-wrap: wrap;
            margin-bottom: 14px;
        }}

        .meta span {{ white-space: nowrap; }}

        .legend {{
            display: flex;
            gap: 20px;
            font-size: 13px;
            padding: 10px 14px;
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 6px;
            width: fit-content;
        }}

        .legend-a {{ color: #1a5fa8; font-weight: 600; }}
        .legend-b {{ color: #1a7a4a; font-weight: 600; }}

        table {{
            width: 100%;
            max-width: 1400px;
            margin: 0 auto;
            border-collapse: collapse;
            background: #fff;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 4px rgba(0,0,0,0.10);
        }}

        thead th {{
            padding: 14px 20px;
            text-align: left;
            font-size: 13px;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            width: 50%;
        }}

        thead th.col-a {{ background: #1a5fa8; color: #fff; }}
        thead th.col-b {{ background: #1a7a4a; color: #fff; }}

        tr.query-row td {{
            padding: 16px 20px 10px;
            background: #f0f4f9;
            border-top: 2px solid #d0d9e8;
            font-weight: 600;
            font-size: 14px;
            color: #0a2240;
            line-height: 1.5;
        }}

        .query-num {{
            display: inline-block;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: #1a5fa8;
            margin-right: 10px;
            vertical-align: middle;
        }}

        tr.response-row td {{
            padding: 16px 20px;
            vertical-align: top;
            border-bottom: 1px solid #e8e8e8;
            font-size: 13.5px;
            line-height: 1.65;
        }}

        td.col-a {{ border-right: 1px solid #e0e8f4; background: #fafdff; }}
        td.col-b {{ background: #f7fdf9; }}

        tr.response-row td h2,
        tr.response-row td h3,
        tr.response-row td h4 {{
            margin: 10px 0 4px;
            color: #0a2240;
        }}

        tr.response-row td ul {{
            margin: 6px 0 6px 18px;
        }}

        tr.response-row td li {{
            margin-bottom: 3px;
        }}

        tr.response-row td code {{
            background: #eef2f7;
            padding: 1px 5px;
            border-radius: 3px;
            font-family: "SF Mono", "Fira Code", monospace;
            font-size: 12px;
        }}

        tr.response-row td strong {{ color: #0a2240; }}

        tr.response-row:last-child td {{ border-bottom: none; }}
    </style>
</head>
<body>
    <div class="report-header">
        <h1>Ascension Clinical Agent — A/B Comparison Report</h1>
        <div class="meta">
            <span>📅 {generated}</span>
            <span>🤖 Model: <strong>{model}</strong></span>
            <span>📄 Prompt: <strong>system_prompt.md</strong></span>
            <span>🔢 Queries: <strong>{total}</strong></span>
        </div>
        <div class="legend">
            <span class="legend-a">A — Without system prompt (baseline)</span>
            <span class="legend-b">B — With Ascension system prompt</span>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th class="col-a">A &mdash; Without System Prompt</th>
                <th class="col-b">B &mdash; With System Prompt</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
</body>
</html>"""


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    # ── Pre-flight checks ──────────────────────────────────────────────────────

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print(f"\n{YELLOW}  GEMINI_API_KEY not set.{RESET}")
        print("  Get a free key at https://aistudio.google.com/app/apikey")
        print("  Then run:  export GEMINI_API_KEY='your-key-here'\n")
        sys.exit(1)

    if not SYSTEM_PROMPT_FILE.exists():
        print(f"\n{RED}  system_prompt.md not found at:{RESET}")
        print(f"  {SYSTEM_PROMPT_FILE}\n")
        sys.exit(1)

    # ── Setup ──────────────────────────────────────────────────────────────────

    system_prompt = load_system_prompt(SYSTEM_PROMPT_FILE)
    genai.configure(api_key=api_key)

    model_a = genai.GenerativeModel(model_name=MODEL)
    model_b = genai.GenerativeModel(model_name=MODEL, system_instruction=system_prompt)

    total = len(TEST_QUERIES)
    print(f"\n{BOLD}  Ascension Clinical Agent — A/B Comparison{RESET}")
    print(f"  {DIM}Model: {MODEL}  |  Queries: {total}{RESET}")
    print(f"  {DIM}System prompt: {SYSTEM_PROMPT_FILE.name}  ({len(system_prompt):,} chars){RESET}\n")

    # ── Run queries ────────────────────────────────────────────────────────────

    results = []
    for i, query in enumerate(TEST_QUERIES):
        print(f"  {DIM}[{i + 1}/{total}] Running...{RESET}", end="\r", flush=True)

        response_a = call_gemini(model_a, query)
        time.sleep(REQUEST_DELAY)

        response_b = call_gemini(model_b, query)
        time.sleep(REQUEST_DELAY)

        results.append({"query": query, "without": response_a, "with": response_b})
        print_result(i, total, query, response_a, response_b)

    # ── Save report ────────────────────────────────────────────────────────────

    report = build_html_report(results, MODEL)
    OUTPUT_FILE.write_text(report, encoding="utf-8")

    hr("═")
    print(f"\n{GREEN}{BOLD}  Done.{RESET} Report saved to:")
    print(f"  {OUTPUT_FILE}\n")

    # ── Auto-score ─────────────────────────────────────────────────────────────
    scorer = Path(__file__).parent / "score_report.py"
    if scorer.exists():
        print(f"{DIM}  Scoring report...{RESET}")
        import subprocess
        result = subprocess.run(
            [sys.executable, str(scorer), str(OUTPUT_FILE)],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            # Print the per-query scores and overall line from scorer output
            for line in result.stdout.splitlines():
                print(f"  {line}")
        else:
            print(f"{YELLOW}  Scoring failed:{RESET} {result.stderr.strip()}")
    else:
        print(f"{DIM}  (score_report.py not found — skipping auto-score){RESET}")


if __name__ == "__main__":
    main()
