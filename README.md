# Ascension Clinical Agent — Brand Voice Research

**WWT × Ascension · Internal Research · May 2026**

A structured research and testing effort to define, validate, and encode the Ascension brand voice into a Vertex AI Gemini clinical agent. Covers vocabulary, tone, data presentation rules, scope guardrails, and iterative prompt refinement across five evaluation runs.

**[View the full research report →](https://kevin-freitas-wwt.github.io/agent-brand-research/)**

---

## What's in this repo

| File | Description |
|---|---|
| [`index.html`](https://kevin-freitas-wwt.github.io/agent-brand-research/) | Landing page — project summary, key findings, and links to all artifacts |
| [`prompt_evolution.html`](https://kevin-freitas-wwt.github.io/agent-brand-research/prompt_evolution.html) | Interactive prompt evolution tracker — word-level diffs, per-query scores across 5 runs |
| [`system_prompt.md`](https://kevin-freitas-wwt.github.io/agent-brand-research/system_prompt.md) | Final Ascension Clinical Agent system instruction (Vertex AI Gemini format) |
| `Ascension Brand Voice Research.docx` | WWT brand voice research — public vs. clinical voice, vocabulary, tone by context |

---

## Results at a glance

The agent's brand voice compliance score across 14 test queries improved from **74% (baseline, no prompt)** to **93% (Run 5)** over five prompt iterations.

| Run | Vocab | Tone | Data | Scope | Action | Overall |
|---|---|---|---|---|---|---|
| Baseline (no prompt) | 78% | 64% | 57% | 79% | 93% | 74% |
| Run 2 — First prompt | 83% | 76% | 71% | 86% | 95% | 82% |
| Run 3 — Tone hardening | 90% | 81% | 76% | 93% | 95% | 87% |
| Run 4 — Data guardrail | 93% | 90% | 95% | 100% | 93% | **94%** |
| Run 5 — Final | 95% | 93% | 100% | 100% | 88% | **93%** |

Scores are rule-based across five dimensions (3 pts each, 15 max per query). See the [prompt evolution tracker](https://kevin-freitas-wwt.github.io/agent-brand-research/prompt_evolution.html) for per-query breakdowns and word-level response diffs.

### What drove the score improvements

- **Run 3:** Hard prohibition on sentimental closing phrases ("those we are privileged to serve") and mission-rationale appended to actionable closes
- **Run 4:** Hard "no fabricated metrics" rule eliminated invented CLABSI rates, fall percentages, and HCAHPS figures; citation specificity requirement (category reference, not invented policy titles)
- **Run 5:** Direct leader / role title distinction; bracket placeholder prohibition; final vocabulary exception tuning

---

## Scoring dimensions

| Dimension | What it measures |
|---|---|
| **Vocabulary** | No banned terms (`employees`, `staff`, `zero-harm`, `supervisor`, `manager`); correct Ascension language |
| **Tone** | Professional, warm, direct; no sentimental flourishes or corporate filler |
| **Data Integrity** | No fabricated metrics or invented policy citations |
| **Scope** | Stays within agent boundaries; explicitly declines clinical advice and chart access requests |
| **Actionability** | Every response closes with a concrete next step for the associate |

---

## Model and tooling

- **Model:** Gemini 2.5 Flash via Google AI Studio API
- **Evaluation:** Rule-based scorer (`score_report.py`) — no LLM-as-judge
- **Test suite:** 14 queries across policy Q&A, clinical metrics, patient safety, identity/scope, and vocabulary edge cases
- **A/B format:** Each query run against baseline Gemini (no prompt) and the current prompt version side-by-side
