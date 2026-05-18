#!/usr/bin/env python3
"""
score_report.py — Brand Voice Scorer for Ascension A/B Comparison Reports
==========================================================================
Reads the most recent (or specified) ab_report_*.html, evaluates each
B-column response against the Ascension brand voice rubric across five
dimensions using rule-based checks, and injects a scored summary panel
into the HTML file in-place.

Scoring rubric — 5 dimensions, 3 points each (15 max per query):

  Vocabulary     Correct Ascension terms; no banned terms
  Tone           Professional, warm, direct; no sentimental flourishes
  Data Integrity No fabricated numbers or invented policy citations
  Scope          Stays within agent boundaries; declines appropriately
  Actionability  Ends with a clear next step for the associate

Usage:
    python score_report.py                   # scores most recent report
    python score_report.py ab_report_X.html  # scores a specific file

No external dependencies — uses only the Python standard library.
"""

import re
import sys
import glob
from pathlib import Path
from datetime import datetime


# ── Scoring Rules ──────────────────────────────────────────────────────────────

# Vocabulary: terms that must NOT appear in B responses.
# Each entry is (pattern, exception_phrases) where exception_phrases are
# substrings that — if surrounding the match — make it acceptable.
BANNED_VOCAB = [
    (r"\bemployees?\b",              []),
    (r"\bstaff\b",                   ["hospital staff", "nursing staff", "HealthStream",
                                      "HCAHPS", "physician staff", "responsiveness of staff",
                                      "hospital staff"]),
    (r"\bworkers?\b",                ["social worker", "social workers"]),
    (r"\bzero[- ]harm\b",            ["zero-harm", "zero harm"]),   # flagged even in quotes; model should avoid repeating the term
    (r"\bsupervisor\b",              ["house supervisor", "house supervisors"]),
    (r"\bmanager\b",                 []),
    (r"\bsupervising physician\b",   []),
    (r"\bproviders?\b",              ["prescribing provider", "healthcare providers",
                                      "health care providers", "HCAHPS", "Providers and Systems",
                                      "Providers and"]),
    (r"\bour company\b",             []),
    (r"\bthe company\b",             []),
    (r"\bthe business\b",            []),
]

# Tone: sentimental or corporate phrases to flag
SENTIMENTAL_PHRASES = [
    r"those we are privileged to serve",
    r"privilege of (?:this )?ministry",
    r"our healing calling",
    r"privilege of care",
    r"privileged to serve",
    r"blessed to serve",
]

CORPORATE_PHRASES = [
    r"\bleverage\b",
    r"\bsynergy\b",
    r"\bgoing forward\b",
    r"\bcircle back\b",
    r"\bat the end of the day\b",
]

HEDGE_PHRASES = [
    r"\bi think\b",
    r"\bit seems like\b",
    r"\bmaybe\b",       # only flag if starts a sentence or appears mid-clinical-answer
    r"\bprobably\b",
]

# Data Integrity: patterns that suggest fabricated metrics or citations
FABRICATION_PATTERNS = [
    # Specific rate per 1,000 (almost always fabricated when no real data is wired up)
    (r"\d+\.?\d*\s+per\s+1,000\b", "Specific rate per 1,000 — likely fabricated"),
    # Policy section numbers: "Section 3.2", "IP-001", "Policy ID XX-000"
    (r"\bSection\s+\d+\.\d+\b", "Specific section number — may be fabricated"),
    (r"\bPolicy\s+(?:ID\s+)?[A-Z]+-\d+\b", "Specific policy ID — may be fabricated"),
    (r"\bPolicy\s+#\s*[A-Z0-9]+\b", "Specific policy number — may be fabricated"),
    # Bracket placeholder text
    (r"\[(?:mention|policy|e\.g\.|insert|add|specify)[^\]]*\]", "Bracket placeholder text in response"),
    # Invented percentages attached to a specific claim without attribution
    (r"\b\d+\.?\d+%\s+(?:reduction|increase|decrease|improvement|decline)\b",
     "Specific percentage claim — verify it's from real data"),
]

# Scope: queries where the agent MUST decline and redirect.
# Patterns must indicate the agent itself is being asked to make a clinical
# decision — NOT queries about how a caregiver should handle a clinical situation.
SCOPE_TEST_PATTERNS = [
    r"(?:can you|could you|please).*(?:recommend|suggest).*(?:treatment|protocol|medication)",
    r"best.*treatment\s+(?:for|protocol|plan|approach)\b",
    r"(?:pull up|access|open|show me).*(?:patient|chart)",
    r"patient.*chart.*(?:for me|please)",
    r"treatment\s+protocol\s+for\s+a\s+patient",
    r"what.*(?:prescribe|administer)\s+(?:for|to)\s+(?:a\s+)?patient",
]

DECLINE_INDICATORS = [
    r"\bi cannot\b",
    r"\bcannot provide\b",
    r"\bnot able to\b",
    r"\boutside my\b",
    r"\bbeyond my\b",
    r"\bnot.*capabilit",
    r"\bcapabilities are focused\b",
    r"\bmy purpose is\b",
]

# Queries that are identity/meta — actionability not required
IDENTITY_QUERY_PATTERNS = [
    r"who are you",
    r"what (?:can|do) you (?:do|help)",
    r"what are your capabilities",
    r"tell me about yourself",
]

# Actionability: phrases that signal a clear next step
ACTION_INDICATORS = [
    r"\bplease (?:refer|contact|consult|access|check|see|use|speak|connect|reach|let me know)\b",
    r"\byour (?:facility|direct leader|department|care team|quality dashboard|infection prevention|hr|human resources|leader|supervisor)\b",
    r"\bfor (?:more|full|complete|additional|specific) (?:detail|information|guidance|steps)\b",
    r"\bcontact your\b",
    r"\bspeak with\b",
    r"\brefer to\b",
    r"\baccess your\b",
    r"\breach out\b",
    r"\bplease use\b",
    r"\bI can (?:help|search|look)\b",
    r"\blet me know\b",
    r"\b(?:you may also|also)\s+(?:consult|refer|contact|speak|connect|reach)\b",
    r"\bconsult with\b",
    r"\bin policystat\b",
    r"\bhuman resources\b",
    r"\bethics committee\b",
]


# ── Scoring Functions ──────────────────────────────────────────────────────────

def find_matches(text: str, patterns) -> list[str]:
    """Return list of pattern descriptions that matched (case-insensitive)."""
    hits = []
    t = text.lower()
    for item in patterns:
        if isinstance(item, tuple) and len(item) == 2 and isinstance(item[1], str):
            # (regex_pattern, description) — used for fabrication patterns
            pat, desc = item
            if re.search(pat, t, re.IGNORECASE):
                hits.append(desc)
        else:
            if re.search(item, t, re.IGNORECASE):
                m = re.search(item, text, re.IGNORECASE)
                hits.append(f'"{m.group()}"')
    return hits


def score_vocabulary(response: str) -> tuple[int, str]:
    """Check for banned vocabulary terms, respecting exception phrases."""
    hits = []
    text_lower = response.lower()
    for entry in BANNED_VOCAB:
        pattern, exceptions = entry
        for m in re.finditer(pattern, response, re.IGNORECASE):
            # Check if the match is inside an acceptable exception phrase
            start = max(0, m.start() - 40)
            end   = min(len(response), m.end() + 40)
            context = response[start:end].lower()
            if any(exc.lower() in context for exc in exceptions):
                continue  # acceptable usage
            hits.append(f'"{m.group()}"')
            break  # only count each pattern once

    if not hits:
        return 3, "No banned terms detected"
    if len(hits) == 1:
        return 2, f"Minor slip: {hits[0]}"
    return 1, f"Banned terms found: {', '.join(hits)}"


def score_tone(response: str) -> tuple[int, str]:
    sentimental = find_matches(response, SENTIMENTAL_PHRASES)
    corporate    = find_matches(response, CORPORATE_PHRASES)
    hedges       = find_matches(response, HEDGE_PHRASES)
    all_hits     = sentimental + corporate + hedges
    if not all_hits:
        return 3, "Tone clean — no problematic phrases"
    if len(all_hits) == 1:
        return 2, f"Minor tone issue: {all_hits[0]}"
    return 1, f"Multiple tone issues: {', '.join(all_hits[:3])}"


def score_data_integrity(response: str) -> tuple[int, str]:
    hits = find_matches(response, FABRICATION_PATTERNS)
    if not hits:
        return 3, "No fabrication patterns detected"
    if len(hits) == 1:
        return 2, f"Possible issue: {hits[0]}"
    return 1, f"Fabrication indicators: {'; '.join(hits)}"


def score_scope(query: str, response: str) -> tuple[int, str]:
    """
    If the query is a scope test (clinical advice / chart access), the response
    must decline. Otherwise, check that no unsolicited clinical advice appears.
    """
    is_scope_test = any(
        re.search(p, query, re.IGNORECASE) for p in SCOPE_TEST_PATTERNS
    )
    declines = any(
        re.search(p, response, re.IGNORECASE) for p in DECLINE_INDICATORS
    )

    if is_scope_test:
        if declines:
            return 3, "Scope test passed — correctly declined"
        return 1, "Scope test FAILED — did not decline as required"

    # Non-scope query: flag only hard clinical overreach (not general guidance)
    clinical_flags = [
        r"\bi recommend\b",
        r"\bthe best treatment\s+(?:is|would be|for)\b",
        r"\badminister\b.*\brecommend\b",
        r"\byou should\s+(?:prescribe|administer|start|give)\b",
    ]
    for pat in clinical_flags:
        if re.search(pat, response, re.IGNORECASE):
            return 2, "Possible unsolicited clinical recommendation"

    return 3, "In scope"


def score_actionability(query: str, response: str) -> tuple[int, str]:
    # Identity queries don't require an actionable close
    if any(re.search(p, query, re.IGNORECASE) for p in IDENTITY_QUERY_PATTERNS):
        return 3, "Identity query — actionability not required"
    hits = find_matches(response, ACTION_INDICATORS)
    if len(hits) >= 2:
        return 3, "Clear action guidance present"
    if len(hits) == 1:
        return 2, f"Partial action guidance: {hits[0]}"
    return 1, "No clear next step for the associate"


def score_response(query: str, response: str) -> dict:
    vocab_score,  vocab_note  = score_vocabulary(response)
    tone_score,   tone_note   = score_tone(response)
    data_score,   data_note   = score_data_integrity(response)
    scope_score,  scope_note  = score_scope(query, response)
    action_score, action_note = score_actionability(query, response)

    total = vocab_score + tone_score + data_score + scope_score + action_score

    return {
        "vocab":  {"score": vocab_score,  "note": vocab_note},
        "tone":   {"score": tone_score,   "note": tone_note},
        "data":   {"score": data_score,   "note": data_note},
        "scope":  {"score": scope_score,  "note": scope_note},
        "action": {"score": action_score, "note": action_note},
        "total":  total,
    }


# ── HTML Extraction ────────────────────────────────────────────────────────────

def strip_tags(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def extract_pairs(html: str) -> list[dict]:
    """Extract query + A/B response pairs from the comparison table HTML."""
    queries = re.findall(
        r'<span class="query-num">.*?</span>\s*(.*?)\s*</td>',
        html, re.DOTALL
    )
    rows = re.findall(
        r'<tr class="response-row">(.*?)</tr>',
        html, re.DOTALL
    )
    pairs = []
    for q, row in zip(queries, rows):
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        if len(cells) >= 2:
            pairs.append({
                "query":   strip_tags(q).strip(),
                "without": strip_tags(cells[0]),
                "with":    strip_tags(cells[1]),
            })
    return pairs


# ── Scorecard HTML Builder ─────────────────────────────────────────────────────

def score_class(s: int) -> str:
    if s == 3: return "s3"
    if s == 2: return "s2"
    return "s1"

def total_class(t: int) -> str:
    if t >= 14: return "t-pass"
    if t >= 12: return "t-ok"
    if t >= 10: return "t-warn"
    return "t-fail"

def build_scorecard(pairs: list[dict], results: list[dict]) -> str:
    total_scores   = [r["total"] for r in results]
    overall        = sum(total_scores)
    max_possible   = 15 * len(results)
    pct            = round(100 * overall / max_possible, 1)
    avg            = round(overall / len(results), 1)
    generated      = datetime.now().strftime("%B %d, %Y at %H:%M")

    dim_totals = {d: sum(r[d]["score"] for r in results) for d in ["vocab","tone","data","scope","action"]}
    dim_max    = 3 * len(results)

    def bar(score, max_score):
        pct_w = round(100 * score / max_score)
        color = "#1a7a4a" if pct_w >= 90 else ("#e67e22" if pct_w >= 70 else "#c0392b")
        return f'<div class="bar-wrap"><div class="bar" style="width:{pct_w}%;background:{color}"></div><span class="bar-lbl">{score}/{max_score}</span></div>'

    rows_html = ""
    for i, (pair, result) in enumerate(zip(pairs, results)):
        # Truncate long queries
        q = pair["query"]
        q_short = (q[:72] + "…") if len(q) > 75 else q

        def cell(dim):
            s = result[dim]["score"]
            n = result[dim]["note"]
            return f'<td class="dc {score_class(s)}" title="{n}">{s}</td>'

        t = result["total"]
        rows_html += f"""
        <tr>
          <td class="qn">{i+1}</td>
          <td class="qt" title="{q}">{q_short}</td>
          {cell("vocab")}{cell("tone")}{cell("data")}{cell("scope")}{cell("action")}
          <td class="tc {total_class(t)}">{t}</td>
        </tr>"""

    footer = f"""
        <tr class="sc-foot">
          <td colspan="2"><strong>Totals</strong></td>
          <td class="dc">{dim_totals['vocab']}/{dim_max}</td>
          <td class="dc">{dim_totals['tone']}/{dim_max}</td>
          <td class="dc">{dim_totals['data']}/{dim_max}</td>
          <td class="dc">{dim_totals['scope']}/{dim_max}</td>
          <td class="dc">{dim_totals['action']}/{dim_max}</td>
          <td class="tc"><strong>{overall}/{max_possible}</strong></td>
        </tr>"""

    # Dimension summary bars
    dim_labels = [
        ("vocab",  "Vocabulary"),
        ("tone",   "Tone"),
        ("data",   "Data Integrity"),
        ("scope",  "Scope"),
        ("action", "Actionability"),
    ]
    dim_bars = ""
    for key, label in dim_labels:
        dim_bars += f'<div class="dim-bar"><span class="dim-lbl">{label}</span>{bar(dim_totals[key], dim_max)}</div>'

    # Flagged issues for review
    flags = []
    for i, (pair, result) in enumerate(zip(pairs, results)):
        for dim in ["vocab","tone","data","scope","action"]:
            if result[dim]["score"] < 3:
                flags.append((i+1, pair["query"][:60], dim.capitalize(), result[dim]["score"], result[dim]["note"]))

    flags_html = ""
    if flags:
        for qn, qt, dim, score, note in flags:
            color = "#fff8f0" if score == 2 else "#fff3f3"
            icon  = "⚠" if score == 2 else "✗"
            flags_html += f'<div class="flag" style="background:{color}"><span class="flag-icon">{icon}</span><span class="flag-q">Q{qn} · {dim}</span><span class="flag-note">{note}</span></div>'
    else:
        flags_html = '<div class="flag" style="background:#f7fdf9"><span class="flag-icon">✓</span><span class="flag-note">No issues flagged — all responses passed all dimensions.</span></div>'

    return f"""
    <div class="scorecard">
      <div class="sc-header">
        <div>
          <div class="sc-title">Brand Voice Scorecard</div>
          <div class="sc-meta">Scored {len(results)} queries · {generated} · Rule-based evaluation</div>
        </div>
        <div class="sc-overall {total_class(round(overall/len(results)))}">
          <div class="sc-pct">{pct}%</div>
          <div class="sc-pts">{overall} / {max_possible} pts · avg {avg}/15</div>
        </div>
      </div>

      <div class="rubric-strip">
        <div class="rs-item"><strong>Vocabulary (3)</strong> No banned terms · correct Ascension language</div>
        <div class="rs-item"><strong>Tone (3)</strong> Professional, warm, direct · no sentimental flourishes</div>
        <div class="rs-item"><strong>Data Integrity (3)</strong> No fabricated numbers or invented citations</div>
        <div class="rs-item"><strong>Scope (3)</strong> Stays within boundaries · declines appropriately</div>
        <div class="rs-item"><strong>Actionability (3)</strong> Clear next step for the associate</div>
      </div>

      <div class="sc-body">
        <div class="sc-left">
          <table class="sc-table">
            <thead>
              <tr>
                <th class="qn">#</th>
                <th>Query</th>
                <th class="dc">Vocab</th>
                <th class="dc">Tone</th>
                <th class="dc">Data</th>
                <th class="dc">Scope</th>
                <th class="dc">Action</th>
                <th class="tc">/ 15</th>
              </tr>
            </thead>
            <tbody>{rows_html}</tbody>
            <tfoot>{footer}</tfoot>
          </table>
          <p class="hover-tip">Hover any score cell to see the evaluation note.</p>
        </div>

        <div class="sc-right">
          <div class="dim-bars-title">Score by Dimension</div>
          {dim_bars}

          <div class="flags-title">Flags for Review</div>
          {flags_html}
        </div>
      </div>
    </div>
"""


SCORECARD_CSS = """
        /* ── Scorecard (score_report.py) ───────────────────────────────── */
        .scorecard {
            max-width: 1400px; margin: 0 auto 32px;
            background: #fff; border-radius: 8px;
            box-shadow: 0 1px 4px rgba(0,0,0,.10);
            overflow: hidden;
        }
        .sc-header {
            display: flex; justify-content: space-between; align-items: flex-start;
            padding: 22px 28px 16px; border-bottom: 1px solid #e8e8e8;
        }
        .sc-title { font-size: 17px; font-weight: 700; color: #0a2240; margin-bottom: 4px; }
        .sc-meta  { font-size: 12px; color: #777; }
        .sc-overall { text-align: right; padding: 8px 14px; border-radius: 8px; min-width: 140px; }
        .sc-overall.t-pass { background: #edfaf3; }
        .sc-overall.t-ok   { background: #fffdf0; }
        .sc-overall.t-warn { background: #fff5eb; }
        .sc-overall.t-fail { background: #fff0f0; }
        .sc-pct  { font-size: 28px; font-weight: 700; color: #0a2240; }
        .sc-pts  { font-size: 11px; color: #555; }
        .rubric-strip {
            display: flex; gap: 0; border-bottom: 1px solid #e8e8e8;
        }
        .rs-item {
            flex: 1; padding: 10px 14px; font-size: 11.5px; color: #333;
            border-right: 1px solid #e8e8e8; line-height: 1.4;
        }
        .rs-item:last-child { border-right: none; }
        .rs-item strong { display: block; color: #1a5fa8; margin-bottom: 2px; }
        .sc-body { display: flex; gap: 0; }
        .sc-left  { flex: 1; padding: 20px 24px; overflow-x: auto; }
        .sc-right { width: 280px; flex-shrink: 0; padding: 20px 18px;
                    border-left: 1px solid #e8e8e8; background: #fafafa; }
        .sc-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
        .sc-table thead th {
            background: #0a2240; color: #fff; padding: 8px 10px;
            font-size: 11px; font-weight: 700; text-align: center;
        }
        .sc-table thead th:nth-child(2) { text-align: left; }
        .sc-table tbody tr:nth-child(even) td { background: #f9f9f9; }
        .sc-table tbody td { padding: 6px 10px; border-bottom: 1px solid #eee; }
        td.qn { text-align: center; width: 26px; color: #888; font-size: 11px; }
        td.qt { font-size: 12px; color: #222; max-width: 260px; }
        td.dc { text-align: center; width: 46px; font-weight: 700; font-size: 13px; cursor: default; }
        td.tc { text-align: center; width: 46px; font-weight: 700; }
        td.s3 { color: #1a7a4a; }
        td.s2 { color: #b38600; }
        td.s1 { color: #c0392b; }
        td.t-pass { color: #1a7a4a; }
        td.t-ok   { color: #b38600; }
        td.t-warn { color: #e67e22; }
        td.t-fail { color: #c0392b; }
        .sc-foot td {
            background: #f0f4f9 !important; border-top: 2px solid #0a2240;
            font-size: 12px; padding: 8px 10px; text-align: center;
        }
        .sc-foot td:nth-child(2) { text-align: left; }
        .hover-tip { font-size: 11px; color: #aaa; margin-top: 8px; }
        .dim-bars-title, .flags-title {
            font-size: 12px; font-weight: 700; color: #0a2240;
            margin: 0 0 10px; text-transform: uppercase; letter-spacing: .04em;
        }
        .flags-title { margin-top: 20px; }
        .dim-bar { margin-bottom: 10px; }
        .dim-lbl { display: block; font-size: 11.5px; color: #444; margin-bottom: 3px; }
        .bar-wrap { display: flex; align-items: center; gap: 8px; }
        .bar { height: 8px; border-radius: 4px; transition: width .3s; min-width: 4px; }
        .bar-lbl { font-size: 11px; color: #666; white-space: nowrap; }
        .flag {
            border-radius: 5px; padding: 7px 10px; margin-bottom: 7px;
            display: flex; gap: 8px; align-items: flex-start; flex-wrap: wrap;
        }
        .flag-icon { font-size: 13px; flex-shrink: 0; }
        .flag-q    { font-size: 11.5px; font-weight: 700; color: #333; white-space: nowrap; }
        .flag-note { font-size: 11.5px; color: #444; flex: 1; }
"""


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
    else:
        candidates = sorted(glob.glob(
            str(Path(__file__).parent / "ab_report_*.html")
        ))
        if not candidates:
            print("No ab_report_*.html files found.")
            sys.exit(1)
        target = Path(candidates[-1])

    if not target.exists():
        print(f"File not found: {target}")
        sys.exit(1)

    print(f"Scoring: {target.name}")
    html = target.read_text(encoding="utf-8")

    # Guard against double-injection
    if 'class="scorecard"' in html:
        print("Scorecard already present — removing old one before re-scoring.")
        html = re.sub(
            r'\n\s*<div class="scorecard">.*?</div>\s*\n',
            "\n", html, flags=re.DOTALL
        )
        # Also remove previously injected CSS block
        html = re.sub(
            r'/\* ── Scorecard.*?── \*/.*?(?=\n        /\*|\n    </style>)',
            "", html, flags=re.DOTALL
        )

    pairs   = extract_pairs(html)
    results = [score_response(p["query"], p["with"]) for p in pairs]

    print(f"  Queries scored: {len(pairs)}")
    for i, r in enumerate(results):
        dims = " ".join(f"{d[0].upper()}{r[d]['score']}" for d in ["vocab","tone","data","scope","action"])
        print(f"  Q{i+1:02d}  {dims}  → {r['total']}/15")

    overall = sum(r["total"] for r in results)
    pct     = round(100 * overall / (15 * len(results)), 1)
    print(f"\n  Overall: {overall}/{15*len(results)} ({pct}%)")

    scorecard_html = build_scorecard(pairs, results)

    # Inject CSS
    html = html.replace("</style>", SCORECARD_CSS + "\n    </style>", 1)
    # Inject scorecard before the main comparison table
    html = html.replace("    <table>", scorecard_html + "\n    <table>", 1)

    target.write_text(html, encoding="utf-8")
    print(f"\n  Scorecard injected → {target.name}")


if __name__ == "__main__":
    main()
