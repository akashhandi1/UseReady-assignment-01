# Metadata Extraction from Rental Agreements - Design Notes

These are the design notes for the project: the dataset findings, the choices I
made, and why. The README covers how to run it; this file covers the reasoning.


## 1. Summary

The goal is to extract six metadata fields from rental agreement documents
(`.docx` or scanned `.png`), without rule-based or RegEx extraction logic, and to
optimise for per-field recall (exact value match).

The approach is a template-agnostic extraction pipeline built around a
vision-capable LLM with structured (JSON-schema) output and a few worked
examples taken from the train set. Images are read directly by the multimodal
model, so there is no OCR step to introduce errors. `.docx` files are parsed to
clean text. A small post-processing layer reformats the output to match the CSV
format the evaluator expects. The whole thing is wrapped in a FastAPI service and
ships with an evaluation harness that reproduces the assignment's recall metric.

This stays within the "no rule-based" constraint because the decision of what
each value is lives in the model, not in hand-written conditions. RegEx is used
only for output formatting (for example, zero-padding a date), never to find or
choose a value.


## 2. Problem Statement

Extract these six fields from any rental agreement, regardless of template:

| # | Field | Type | Example |
|---|-------|------|---------|
| 1 | Agreement Value | integer (monthly rent) | `9000` |
| 2 | Agreement Start Date | date `DD.MM.YYYY` | `01.04.2010` |
| 3 | Agreement End Date | date `DD.MM.YYYY` | `31.03.2011` |
| 4 | Renewal Notice (Days) | integer days | `60` |
| 5 | Party One | string (lessor / owner) | `P C MATHEW` |
| 6 | Party Two | string (lessee / tenant) | `L GOPINATH` |

- Input: a single `.docx` or `.png` file.
- Constraint: no rule-based / RegEx / static-condition extraction logic.
- Metric: per-field recall = `exact_matches / (exact_matches + misses)`.


## 3. Dataset Analysis

### 3.1 What is on disk vs. what the CSVs claim

`train/` folder (10 files):

| File | Format | In train.csv? | Notes |
|------|--------|---------------|-------|
| 18325926-Rental-Agreement-1 | docx | yes | |
| 36199312-Rental-Agreement | png | yes | needs OCR/vision |
| 44737744-...-Rental-Agreement | docx | yes | renewal notice blank in label |
| 46239065-Standard-Rental-...-Performance-Fee | docx | no, unlabeled | extra file, no ground truth |
| 47854715-RENTAL-AGREEMENT | docx | yes | |
| 50070534-RENTAL-AGREEMENT | docx | yes | |
| 54770958-Rental-Agreement | png | yes | needs OCR/vision |
| 54945838-Rental-Agreement | png | yes | needs OCR/vision |
| 6683127-House-Rental-Contract-...-Page-1 | docx | yes | near-duplicate of 6683129 |
| 6683129-House-Rental-Contract-... | docx | yes | near-duplicate of 6683127 |

`test/` folder (4 files): all four are present and labeled in `test.csv`:
`24158401` (png), `95980236` (png), `156155545` (`.pdf.docx`), `228094620`
(`.pdf.docx`).

### 3.2 Findings that drive the design

1. **End dates are derived, not present in the text.** The `47854715` text says
   "11 months starting from 1 April 2010"; the label end date is `31.02.2011`, a
   date that is invalid (Feb has no 31st) and appears nowhere in the document.
   The annotator computed `start + term` and made arithmetic and formatting
   errors. So the end date needs reasoning, and exact-match recall on it is
   capped by label noise.

2. **Renewal Notice needs a unit conversion.** Image `36199312` says "informed
   within one month prior notice"; the label is `30`. So "one month" maps to 30,
   "two months" to 60, and so on. This is reasoning, not span extraction.

3. **Label noise is significant.** There are invalid dates (`31.11.2009`,
   `31.04.2011`, `31.02.2011`), leading/trailing spaces in party names
   (`" P C MATHEW"`, `"L GOPINATH "`), and value words that contradict the digits
   in the body (doc `47854715` says "Nine Thousand" then "Seven thousand" for the
   same Rs. 9000). A perfect recall score is not achievable; we optimise toward
   the labels as written.

4. **Train/test leakage and mismatch.** `24158401` appears in both `train.csv`
   and `test.csv` and physically lives in `test/`. `46239065` is in `train/` but
   has no label. Both are handled explicitly so we never train on test.

5. **Two clean format buckets.** Every `.docx` (including the `.pdf.docx` files)
   has extractable text and no embedded images; only the four `.png` files need
   OCR/vision. So routing by file type is simple and deterministic.

6. **Tiny dataset.** About 9 usable labeled train rows and 4 test rows.
   Fine-tuning is not an option at this size; zero/few-shot with a strong
   pretrained model is the sensible route.

### 3.3 Ground-truth schema (exact CSV columns)

```
File Name, Aggrement Value, Aggrement Start Date, Aggrement End Date,
Renewal Notice (Days), Party One, Party Two
```

The source spells it "Aggrement"; the output CSV has to match these headers
exactly.


## 4. Key Insights and Design Implications

| Insight | Design implication |
|---|---|
| Fields need reasoning (date math, unit conversion), not just lookup | Use a reasoning-capable model (LLM), not extractive QA or NER |
| No rule-based extraction allowed | Decision logic lives in the model; code only does I/O and formatting |
| Template-agnostic requirement | Zero/few-shot prompting generalises across templates; no per-template code |
| Exact-match metric with noisy labels | Add a normalization and evaluation harness; report recall with and without lenient matching to separate true errors from label noise |
| Tiny dataset | No training; use train rows as few-shot examples instead |
| docx is text, png is image | Type-routed ingestion; the multimodal model reads png, a parser reads docx |


## 5. Decision Log

### D1 - Core extraction engine
- Options: (A) a vision+text LLM with structured output and few-shot; (B) a
  layout transformer (LayoutLMv3 / Donut) fine-tuned; (C) extractive QA
  (RoBERTa-SQuAD) plus post-logic.
- Chosen: (A), an LLM with structured output.
- Why: it handles the derived fields (date math, "one month" to 30) that B and C
  cannot, and it needs no training (the data is too small for B). It is
  template-agnostic and not rule-based. B and C would still need hand-written
  rules for the renewal and end-date fields, which breaks the constraint and
  performs worse.

### D2 - Which LLM
- Chosen: Google Gemini multimodal API (`gemini-2.5-flash` by default,
  `gemini-2.5-pro` configurable for higher accuracy), via the `google-genai` SDK.
- Why: it is natively multimodal (reads the `.png` scans directly, no OCR), it
  reasons well enough for the derived fields, and it supports structured JSON
  output via `response_schema`. The key is supplied through the `GEMINI_API_KEY`
  environment variable.

### D3 - Image handling (png)
- Options: (A) feed the image directly to a vision LLM (no OCR); (B) Tesseract
  OCR to text, then the LLM.
- Chosen: (A), direct vision, with (B) as an automatic fallback if no vision
  model is configured.
- Why: it avoids OCR errors propagating downstream, and vision models can use
  layout cues (signature blocks help identify Party One and Two). Tesseract on
  these low-contrast scans is error-prone.

### D4 - docx parsing
- Chosen: `python-docx` for paragraphs and tables (some agreements use tables).
  This is plain text extraction, not a rule.

### D5 - Few-shot examples
- Chosen: include 2-3 labeled train documents (text plus their CSV answers) in
  the prompt as worked examples, excluding any test file and excluding `24158401`
  from the examples (it leaks into test).

### D6 - Output normalization
- Dates to `DD.MM.YYYY` (zero-padded, dots). Value to a bare integer (strip `Rs`,
  commas, `/-`). Renewal to an integer. Parties trimmed.
- This is formatting of a value the model produced, not value extraction.

### D7 - End-date strategy (the hardest field)
- Chosen: ask the model for the end date and let it reason from `start + term`.
  Accept that label noise caps exact recall here, and report it transparently.

### D8 - Evaluation
- Chosen: re-implement the assignment's per-field recall exactly (exact string
  match against the CSV). Additionally report a lenient recall
  (trim/case/whitespace-insensitive, date-equivalence) to separate model errors
  from label-noise penalties. The headline number is the strict one.


## 6. Solution Architecture

```
   input file (.docx or .png)
              |
              v
   1. Ingestion and type routing
        .docx -> python-docx text extraction
        .png  -> vision model input (OCR fallback available)
              |
              v
   2. Field extraction engine (LLM)
        structured JSON schema (6 fields)
        few-shot examples from the train set
        reasoning for end date and renewal notice
              |
              v
   3. Post-processing / normalization
        date format, value cleanup, trim
              |
              v
   4. Output: JSON -> predictions.csv

   The same pipeline is exposed two ways:
     - FastAPI /extract endpoint (REST wrapper)
     - evaluation harness (per-field recall)
```


## 7. Component Design

### 7.1 Ingestion and routing (`src/ingest.py`)
- Detect the extension and dispatch.
- `.docx`: extract all paragraph and table text, preserve reading order, light
  whitespace cleanup.
- `.png`: load bytes; if a vision model is active, pass the image directly,
  otherwise fall back to OCR.
- Returns a normalized `DocumentInput {file_name, modality, text?, image_bytes?}`.

### 7.2 Extraction engine (`src/extractor.py`)
- A provider-agnostic interface `BaseExtractor.extract(doc) -> dict`.
- The Gemini extractor builds the prompt from the system instructions, the
  few-shot examples, and the target document, and requests structured JSON
  matching the six-field schema.
- The prompt defines each field, the date format, the months-to-days rule for
  renewal, and the "compute end = start + term" guidance, as instructions to the
  model rather than code branches.

### 7.3 Few-shot examples (`src/prompts.py`)
- A few curated train docs with their gold answers, chosen to cover both a
  "1 year" and an "11 months" term so the model sees the end-date pattern.

### 7.4 Normalization (`src/normalize.py`)
- Pure formatting of the model output to match the CSV conventions (D6).
  Unit-tested.

### 7.5 Output (`src/predict.py`)
- Batch-run over a folder, writing `outputs/predictions.csv` with the exact gold
  headers.


## 8. Evaluation Methodology (`src/evaluate.py`)

- Load the `test.csv` gold labels and `predictions.csv`.
- Strict recall per field: exact string equality (the headline metric, matching
  the assignment).
- Lenient recall per field: after trim, case-fold, and date canonicalisation (a
  diagnostic).
- Output a per-field table, a macro average, and a per-document report (predicted
  vs. gold) so it is clear which errors are model errors and which are label
  noise.

High recall is expected on Value, Start Date, and Party One/Two; lower on End
Date (label noise) and Renewal Notice (often implicit).


## 9. REST API (`src/api.py`)

- Framework: FastAPI and Uvicorn.
- `POST /extract`: multipart file upload (`.docx` or `.png`), returns JSON of the
  six fields.
- `GET /health`.
- Swagger UI served at `/docs`.


## 10. Repository Structure

```
assignment-1/
  README.md            solution approach, run instructions, recall scores, predictions
  PROJECT_PLAN.md      this file
  requirements.txt
  .env.example         API key placeholder
  data/                provided dataset (train/, test/, csvs) - untouched
  src/
    config.py          paths, headers, model config
    schema.py          Pydantic output schema (6 fields)
    ingest.py          type routing and docx/png loading
    extractor.py       LLM extraction engine (provider-agnostic)
    prompts.py         system prompt and few-shot examples
    normalize.py       output formatting to CSV conventions
    predict.py         batch runner -> predictions.csv
    evaluate.py        per-field recall (strict and lenient)
    api.py             FastAPI service
  outputs/
    predictions.csv    test-set predictions
  tests/
    test_normalize.py  unit tests for the formatting layer
```


## 11. Tech Stack

- Python 3.10+
- `python-docx` (docx parsing), `Pillow` (image I/O)
- `google-genai` (the Gemini SDK); `pytesseract` for the optional offline mode
- `pandas` (CSV and evaluation), `fastapi` + `uvicorn` + `python-multipart` (API)
- `pytest` (tests)


## 12. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Label noise caps exact recall, especially on End Date | Lower headline score | Report strict and lenient recall; document it in the README |
| OCR/vision misreads faint scans | Wrong Value or Party | Use the direct vision model; spot-check the four test images |
| Model returns a value not in the document | False positive | Require a blank when not found; temperature 0; ask for a source note |


## 13. Possible Future Improvements

- Fine-tune LayoutLMv3 or Donut if a larger labeled corpus becomes available.
- Confidence scores and a human-in-the-loop review queue for low-confidence
  fields.
- An active-learning loop to grow the labeled set from production traffic.
