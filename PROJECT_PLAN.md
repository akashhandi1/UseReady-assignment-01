# Metadata Extraction from Rental Agreements — End‑to‑End Project Plan

> **Author:** ML Engineering
> **Status:** DRAFT — awaiting review before implementation
> **Date:** 2026‑06‑28

---

## 0. TL;DR (Executive Summary)

Build an **AI/ML system** that extracts 6 metadata fields from rental‑agreement documents
(`.docx` or scanned `.png`), **without rule‑based/RegEx logic**, optimised for **per‑field recall
(exact value match)**.

**Recommended approach:** a *template‑agnostic, layout‑aware extraction pipeline* driven by a
**vision‑capable Large Language Model (LLM) with structured (JSON‑schema) output and few‑shot
examples mined from the train set**. Images are read directly by the multimodal model (no brittle
OCR step); `.docx` files are parsed to clean text. A thin post‑processing layer normalises the
output to the exact CSV format the evaluator expects. The whole system is wrapped in a **FastAPI
REST service** and ships with an **evaluation harness** that reproduces the assignment's recall
metric.

This satisfies the "no rule‑based approach" constraint because the *intelligence* lives in a
learned model, not hand‑written conditions. RegEx is used **only** as a cosmetic output‑formatting
step (e.g. zero‑padding a date), never to locate or decide a value.

---

## 1. Problem Statement (restated)

Extract the following 6 fields from any rental agreement, regardless of template:

| # | Field | Type | Example |
|---|-------|------|---------|
| 1 | Agreement Value | integer (monthly rent) | `9000` |
| 2 | Agreement Start Date | date `DD.MM.YYYY` | `01.04.2010` |
| 3 | Agreement End Date | date `DD.MM.YYYY` | `31.03.2011` |
| 4 | Renewal Notice (Days) | integer days | `60` |
| 5 | Party One | string (lessor / owner) | `P C MATHEW` |
| 6 | Party Two | string (lessee / tenant) | `L GOPINATH` |

**Inputs:** a single `.docx` **or** `.png` file.
**Constraint:** ❌ No rule‑based / RegEx / static‑condition extraction logic.
**Metric:** Per‑field **Recall** = `Exact_Matches / (Exact_Matches + Misses)`.

---

## 2. Dataset Analysis & Findings

### 2.1 Inventory (what is actually on disk vs. what the CSVs claim)

**`train/` folder (10 files):**

| File | Format | In `train.csv`? | Notes |
|------|--------|-----------------|-------|
| 18325926-Rental-Agreement-1 | docx | ✅ | |
| 36199312-Rental-Agreement | png | ✅ | needs OCR/vision |
| 44737744-…-Rental-Agreement | docx | ✅ | renewal notice **blank** in label |
| 46239065-Standard-Rental-…-Performance-Fee | docx | ❌ **unlabeled** | extra file, no ground truth |
| 47854715-RENTAL-AGREEMENT | docx | ✅ | |
| 50070534-RENTAL-AGREEMENT | docx | ✅ | |
| 54770958-Rental-Agreement | png | ✅ | needs OCR/vision |
| 54945838-Rental-Agreement | png | ✅ | needs OCR/vision |
| 6683127-House-Rental-Contract-…-Page-1 | docx | ✅ | near‑duplicate of 6683129 |
| 6683129-House-Rental-Contract-… | docx | ✅ | near‑duplicate of 6683127 |

**`test/` folder (4 files):** all 4 are present and labeled in `test.csv`:
`24158401` (png), `95980236` (png), `156155545` (`.pdf.docx`), `228094620` (`.pdf.docx`).

### 2.2 Data‑quirk findings (these drive the design decisions)

1. **End dates are DERIVED, not present in the text.**
   `47854715` text says *"11 months starting from 1 April 2010"*; the label end date is
   `31.02.2011` — a date that (a) is invalid (Feb has no 31st) and (b) appears nowhere in the
   document. The annotator computed `start + term` and made arithmetic/formatting errors.
   → **End date requires reasoning, and exact‑match recall on it is inherently capped by label
   noise.**

2. **Renewal Notice requires unit conversion.**
   Image `36199312` says *"informed within one month prior notice"*; label = `30`.
   So `"one month" → 30`, `"two months" → 60`, etc. → reasoning, not span extraction.

3. **Label noise is significant.** Invalid dates (`31.11.2009`, `31.04.2011`, `31.02.2011`),
   trailing/leading spaces in party names (`" P C MATHEW"`, `"L GOPINATH "`), value words that
   contradict digits in the body (doc `47854715` body: "Nine Thousand" then "Seven thousand" for
   the same Rs.9000). → **A perfect recall score is not achievable; we optimise toward the labels
   as written.**

4. **Train/Test leakage & mismatch.** `24158401` appears in **both** `train.csv` and `test.csv`
   and physically lives in `test/`. `46239065` is in `train/` but has no label.
   → handle explicitly; never silently train on test.

5. **Two clean format buckets — verified.** Every `.docx` (including the `.pdf.docx` files) has
   extractable text and **zero embedded images**; only the 4 `.png` files need OCR/vision.
   → simple, deterministic routing by file type.

6. **Tiny dataset.** ~9 usable labeled train rows, 4 test rows. → **Fine‑tuning is off the table;**
   zero/few‑shot with a strong pretrained model is the only sensible route.

### 2.3 Ground‑truth schema (exact CSV columns)

```
File Name, Aggrement Value, Aggrement Start Date, Aggrement End Date,
Renewal Notice (Days), Party One, Party Two
```
(Note the source's spelling "Aggrement" — our output CSV must match these headers byte‑for‑byte.)

---

## 3. Key Insights → Design Implications

| Insight | Design implication |
|---|---|
| Fields need *reasoning* (date math, unit conversion), not just lookup | Use a **reasoning‑capable model (LLM)**, not pure extractive QA / NER |
| No rule‑based allowed | Decision logic lives in the **model**; code only does I/O + formatting |
| Template‑agnostic requirement | **Zero/few‑shot prompting** generalises across templates; no per‑template code |
| Exact‑match metric + noisy labels | Add a **normalization + evaluation harness**; report recall with and without lenient matching to diagnose true vs. label‑noise errors |
| Tiny data | **No training**; mine train rows as **few‑shot exemplars** instead |
| docx = text, png = image | **Type‑routed ingestion**; multimodal model reads png, parser reads docx |

---

## 4. Decision Log (each decision, options considered, choice, rationale)

> These are the decisions I want **reviewed/confirmed** before coding.

### D1 — Core extraction engine
- **Options:** (A) Vision+Text LLM with structured output & few‑shot; (B) Layout transformer
  (LayoutLMv3 / Donut) fine‑tuned; (C) Extractive QA (RoBERTa‑SQuAD) + post‑logic.
- **Chosen: (A) LLM with structured output.**
- **Why:** Handles derived fields (date math, "one month"→30) that B/C cannot; needs no training
  (data too small for B); template‑agnostic; not rule‑based. B/C would still need hand‑rules for
  renewal/end‑date — violating the constraint and underperforming.

### D2 — Which LLM / provider  ✅ DECIDED (reviewer)
- **Chosen: Google Gemini multimodal API** (`gemini-2.5-flash` default; `gemini-2.5-pro`
  configurable for max accuracy), via the `google-genai` SDK.
- **Why:** Native multimodal (reads `.png` scans directly, no OCR), strong reasoning for derived
  fields, structured JSON output via `response_schema`. Key supplied via `GEMINI_API_KEY` env var.

### D3 — Image handling (png)
- **Options:** (A) Feed image directly to a vision LLM (no OCR); (B) Tesseract OCR → text → LLM.
- **Chosen: (A) direct vision**, with (B) as an automatic fallback if no vision model is
  configured.
- **Why:** Avoids OCR error propagation; vision models use layout cues (signature blocks identify
  Party One/Two). Tesseract on these low‑contrast Indian rental scans is error‑prone.

### D4 — docx parsing
- **Chosen:** `python-docx` for paragraphs **and tables** (some agreements use tables), with a
  raw‑XML text fallback. Not a "rule" — pure text extraction.

### D5 — Few‑shot exemplar strategy
- **Chosen:** Include 2–3 labeled train documents (text + their CSV answers) in the prompt as
  worked examples, **explicitly excluding any test file** and excluding `24158401` from the train
  exemplars (since it leaks into test). Optionally retrieve the most similar train doc per query
  (lightweight similarity) — decision deferred (see D9).

### D6 — Output normalization (the one place "formatting" code lives)
- Dates → `DD.MM.YYYY` (zero‑padded, dots). Value → bare integer (strip `Rs`, commas, `/-`).
  Renewal → integer. Parties → trimmed string.
- **Note:** This is *presentation formatting of a model‑produced value*, not value *extraction*.
  We will document this clearly to stay within the "no rule‑based" spirit.

### D7 — End‑date strategy (the hardest field)
- **Chosen:** Ask the model for the end date and let it reason from `start + term`; **also** record
  the literal term ("11 months"/"1 year"). Accept that label noise caps exact recall here; report
  it transparently.

### D8 — Evaluation
- **Chosen:** Re‑implement the assignment's per‑field recall exactly (exact string match against
  CSV). Additionally report a **lenient** recall (trim/case/whitespace‑insensitive, date‑equivalence)
  to separate *model errors* from *label‑noise penalties*. Headline number = the strict one.

### D9 — Few‑shot retrieval (dynamic) vs. fixed exemplars — **DEFERRED to reviewer**
- Fixed 2–3 exemplars is simplest and likely sufficient at this scale. Dynamic retrieval adds
  complexity for marginal gain on 4 test docs. Leaning **fixed**.

---

## 5. Solution Architecture

```
                ┌──────────────────────────────────────────────────────┐
   Upload       │                  EXTRACTION PIPELINE                  │
 (.docx/.png) ─►│                                                      │
                │  1. Ingestion & Type Routing                         │
                │        ├─ .docx ─► python-docx text extractor        │
                │        └─ .png  ─► (vision model input | OCR fallback)│
                │                                                      │
                │  2. Field Extraction Engine (LLM)                    │
                │        • structured JSON schema (6 fields)           │
                │        • few-shot exemplars from train set           │
                │        • reasoning for end-date & renewal-notice     │
                │                                                      │
                │  3. Post-processing / Normalization                  │
                │        • date format, value cleanup, trim            │
                │                                                      │
                │  4. Output: JSON  ─►  predictions.csv                 │
                └──────────────────────────────────────────────────────┘
                                  ▲                     │
                                  │                     ▼
                          FastAPI /extract       Evaluation Harness
                          (REST wrapper)         (per-field recall)
```

---

## 6. Component Design (detail)

### 6.1 Ingestion & Routing (`src/ingest.py`)
- Detect extension → dispatch.
- `.docx`: extract all paragraph + table text, preserve reading order, light whitespace cleanup.
- `.png`: load bytes; if a vision model is active, pass image directly; else OCR fallback.
- Returns a normalized `DocumentInput {file_name, modality, text?, image_bytes?}`.

### 6.2 Extraction Engine (`src/extractor.py`)
- Provider‑agnostic interface `BaseExtractor.extract(doc) -> FieldSet`.
- `LLMExtractor`: builds a prompt = system instructions + few‑shot exemplars + the target doc;
  requests **structured JSON** (tool/`response_format`) matching the 6‑field schema; includes a
  short rationale per field (for debugging, stripped from final output).
- Prompt explicitly defines each field, the date format, the "convert months→days" rule for
  renewal, and "compute end = start + term" guidance — as *instructions to a learned model*, not
  as code branches.

### 6.3 Few‑shot exemplars (`src/prompts.py`)
- 2–3 curated train docs with their gold answers; chosen to cover both modalities and both a
  "1 year" and an "11 months" term so the model sees the end‑date pattern.

### 6.4 Normalization (`src/normalize.py`)
- Pure formatting of model output to match CSV conventions (D6). Unit‑tested.

### 6.5 Output (`src/predict.py`)
- Batch‑run over a folder → `outputs/predictions.csv` with the exact gold headers.

---

## 7. Evaluation Methodology (`src/evaluate.py`)

- Load `test.csv` gold + `predictions.csv`.
- **Strict recall** per field = exact string equality (headline metric, matches assignment).
- **Lenient recall** per field = after trim/case‑fold + date canonicalisation (diagnostic).
- Output a per‑field table + macro average + a per‑document error report (predicted vs. gold) so we
  can see exactly which errors are model vs. label noise.
- Also run a quick **train self‑check** (leave‑one‑out style on the 9 labeled train docs) to sanity‑
  check the prompt before touching test.

**Expected reality:** high recall on Value, Start Date, Party One/Two; lower on End Date (label
noise) and Renewal Notice (sparse/implicit). We will report honestly.

---

## 8. REST API (`src/api.py`) — *optional per brief, we include it*

- **Framework:** FastAPI + Uvicorn.
- **Endpoint:** `POST /extract` — multipart file upload (`.docx`/`.png`) → JSON of 6 fields.
- **Endpoint:** `GET /health`.
- Swagger UI auto‑served at `/docs`.
- Example `curl` documented in README.

---

## 9. Repository Structure

```
assignment-1/
├── README.md                 # solution approach, run instructions, recall scores, test predictions
├── PROJECT_PLAN.md           # this file
├── requirements.txt
├── .env.example              # API key placeholder (if hosted model used)
├── data/                     # provided (train/ test/ csvs) — untouched
├── src/
│   ├── ingest.py             # type routing + docx/png loading
│   ├── extractor.py          # LLM extraction engine (provider-agnostic)
│   ├── prompts.py            # system prompt + few-shot exemplars
│   ├── normalize.py          # output formatting to CSV conventions
│   ├── predict.py            # batch runner -> predictions.csv
│   ├── evaluate.py           # per-field recall (strict + lenient)
│   └── api.py                # FastAPI service
├── notebooks/
│   └── exploration.ipynb     # EDA + worked examples (optional)
├── outputs/
│   └── predictions.csv       # test-set predictions (deliverable)
└── tests/
    └── test_normalize.py     # unit tests for formatting layer
```

---

## 10. Tech Stack

- **Python 3.10+**
- `python-docx` (docx parsing), `Pillow` (image I/O)
- LLM SDK: `anthropic` (default) — pluggable; optional `pytesseract`/`ollama` for offline mode
- `pandas` (CSV/eval), `fastapi` + `uvicorn` + `python-multipart` (API)
- `pytest` (tests)

---

## 11. Implementation Phases / Milestones

| Phase | Deliverable | Est. |
|------|-------------|------|
| P0 | Repo scaffold, requirements, config, EDA notebook | 0.5 d |
| P1 | Ingestion (docx + png routing) | 0.5 d |
| P2 | LLM extraction engine + prompt + few‑shot | 1 d |
| P3 | Normalization + batch predict → predictions.csv | 0.5 d |
| P4 | Evaluation harness (strict+lenient) + tuning prompt to maximise recall | 1 d |
| P5 | FastAPI wrapper | 0.5 d |
| P6 | README (approach, run steps, scores, predictions) + cleanup | 0.5 d |

---

## 12. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Label noise caps exact recall (esp. End Date) | Lower headline score | Report strict + lenient; document in README |
| No API key allowed by reviewer | Default path unusable | Pluggable offline provider (Tesseract + local VLM) |
| OCR/vision misreads faint scans | Wrong Value/Party | Direct vision model; manual spot‑check on 4 test imgs |
| Model hallucinates a value not in doc | False positive | Require model to return `null`/blank when not found; low‑temp; ask for source snippet |
| "No rule‑based" interpreted strictly (even formatting) | Compliance question | Keep formatting layer minimal + clearly documented as post‑processing, not extraction |

---

## 13. Future Improvements (note in README)
- Fine‑tune LayoutLMv3 / Donut if a larger labeled corpus becomes available.
- Confidence scores + human‑in‑the‑loop review queue for low‑confidence fields.
- Active‑learning loop to grow the labeled set from production traffic.

---

## 14. Open Questions for Reviewer (please confirm before I implement)

1. **Q1 — Model/provider:** Is using a **hosted LLM API** (Anthropic Claude) acceptable, or must
   the solution run **fully offline / open‑source only** (local VLM + Tesseract)? *(Default: hosted
   Claude with pluggable offline mode.)*
2. **Q2 — "No rule‑based" strictness:** Do you agree a minimal **output‑formatting** layer (date
   zero‑padding, stripping "Rs"/commas) is acceptable, since the *value decision* is the model's?
3. **Q3 — Deliverable format:** Python scripts + README (recommended) **or** a single Jupyter
   notebook?
4. **Q4 — Few‑shot retrieval:** Fixed exemplars (simpler, recommended) vs. dynamic similarity
   retrieval (D9)?
5. **Q5 — REST API:** Include the FastAPI service (it's optional in the brief) — confirm yes.

---

*End of plan. On approval I will scaffold the repo and implement Phases P0→P6.*
