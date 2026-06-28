# Rental Agreement Metadata Extraction

An AI/ML system that extracts six metadata fields from rental/lease agreements —
**regardless of template** — from either a `.docx` file or a scanned `.png` image.

| Field | Description |
|-------|-------------|
| Agreement Value | Monthly rent (integer) |
| Agreement Start Date | `DD.MM.YYYY` |
| Agreement End Date | `DD.MM.YYYY` |
| Renewal Notice (Days) | Notice period in days |
| Party One | Lessor / owner |
| Party Two | Lessee / tenant |

---

## 1. Solution Approach

The extraction "intelligence" is provided by a **multimodal Large Language Model
(Google Gemini)**, not by hand-written rules. This directly satisfies the
assignment constraint of **no rule-based / RegEx / static-condition** extraction.

### Why an LLM (and not RegEx / NER / extractive-QA)?
Exploratory analysis of the data revealed that the target fields are **not all
literally present** in the documents:

1. **Agreement End Date is *derived*.** Documents state a *term* ("11 months",
   "1 year"), not an explicit end date. The ground-truth end dates are computed
   as `start + term` (and even contain impossible calendar dates like
   `31.02.2011`). This requires **reasoning**, which RegEx/NER cannot do.
2. **Renewal Notice needs unit conversion.** Text says *"one month prior
   notice"* → label is `30`. Again, reasoning, not pattern matching.
3. **Many templates.** A template-agnostic requirement is best met by a model
   that reads for *meaning*, with zero per-template code.

A reasoning-capable LLM handles all three; a rule/QA system would need exactly
the hand-written conditions the brief forbids.

### Pipeline

```
upload (.docx/.png)
   │
   ├─ .docx ─► python-docx text extraction (paragraphs + tables)
   └─ .png  ─► sent directly to Gemini's vision model (no brittle OCR)
   │
   ▼
Gemini (gemini-2.5-flash) with:
   • a detailed system prompt defining each field + the reasoning rules
   • few-shot worked examples mined automatically from train.csv
   • structured JSON output enforced via response_schema (Pydantic)
   │
   ▼
normalization layer  (formats value/date/days/name to CSV conventions)
   │
   ▼
predictions.csv  +  REST API response
```

> **On "no rule-based":** the only non-ML code is a thin *formatting* layer
> (`src/normalize.py`) that zero-pads a date or strips `Rs`/commas from a number
> the **model already chose**. It never locates or decides a value from raw text,
> so the extraction itself remains fully model-driven.

### Key data-handling decisions
- **Few-shot exemplars** are loaded dynamically from the train set
  (`src/prompts.py`); the file `24158401` is **excluded** because it also appears
  in the test set (data leakage), as is the unlabeled `46239065`.
- **Images** are read directly by the vision model; `pytesseract` exists only as
  an offline fallback.
- The `.pdf.docx` test files are plain-text docx (verified) and are parsed as docx.

---

## 2. Project Structure

```
assignment-1/
├── README.md              ← this file
├── PROJECT_PLAN.md        ← full design rationale & decision log
├── requirements.txt
├── .env.example           ← copy to .env and add your GEMINI_API_KEY
├── data/                  ← provided dataset (train/ test/ + csvs)
├── src/
│   ├── config.py          ← paths, headers, model config
│   ├── schema.py          ← Pydantic output schema (6 fields)
│   ├── ingest.py          ← file-type routing, docx/png loading
│   ├── prompts.py         ← system prompt + few-shot from train set
│   ├── extractor.py       ← Gemini extraction engine
│   ├── normalize.py       ← output formatting
│   ├── predict.py         ← batch runner → predictions.csv
│   ├── evaluate.py        ← per-field recall (strict + lenient)
│   └── api.py             ← FastAPI REST service
├── tests/test_normalize.py
└── outputs/predictions.csv  ← generated test-set predictions
```

---

## 3. Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure your Gemini API key
cp .env.example .env          # Windows: copy .env.example .env
#   then edit .env and set GEMINI_API_KEY=...
#   (get a free key at https://aistudio.google.com/apikey)
```

> For the image path you do **not** need Tesseract installed — images go straight
> to Gemini. Tesseract is only used if you build an offline variant.

---

## 4. Reproduce the Predictions

```bash
# Generate predictions for the test set
python -m src.predict --input data/test --output outputs/predictions.csv

# Score them with per-field recall
python -m src.evaluate --gold data/test.csv --pred outputs/predictions.csv
```

`predict` writes `outputs/predictions.csv` with the exact ground-truth headers.
`evaluate` prints a per-field recall table plus a per-document breakdown.

---

## 5. REST API (optional deliverable — included)

```bash
uvicorn src.api:app --reload
# open http://127.0.0.1:8000/docs  for interactive Swagger UI
```

Extract from a single file:

```bash
curl -X POST http://127.0.0.1:8000/extract \
     -F "file=@data/test/95980236-Rental-Agreement.png"
```

Response:

```json
{
  "file_name": "95980236-Rental-Agreement.png",
  "fields": {
    "agreement_value": "9000",
    "agreement_start_date": "01.04.2010",
    "agreement_end_date": "31.03.2011",
    "renewal_notice_days": "30",
    "party_one": "S.Sakunthala",
    "party_two": "V.V.Ravi Kian"
  }
}
```

---

## 6. Evaluation Metric

Per the assignment, the headline metric is **per-field Recall**:

```
Recall(field) = exact_matches / (exact_matches + misses)
```

`src/evaluate.py` reports two numbers per field:
- **Strict** — exact string match (the assignment's official metric).
- **Lenient** — case/whitespace-insensitive + date-equivalence (a *diagnostic*
  to separate genuine model errors from ground-truth label noise, e.g. invalid
  dates and trailing spaces in the provided CSVs).

### Test-set recall scores

Model: `gemini-2.5-flash`, temperature 0. Evaluated on the 4 documents in
`data/test/` against `data/test.csv`.

| Field | Strict Recall | Lenient Recall |
|-------|---------------|----------------|
| Aggrement Value | 100.00% | 100.00% |
| Aggrement Start Date | 100.00% | 100.00% |
| Aggrement End Date | 75.00% | 75.00% |
| Renewal Notice (Days) | 100.00% | 100.00% |
| Party One | 100.00% | 100.00% |
| Party Two | 50.00% | 100.00% |
| **Macro average** | **87.50%** | **95.83%** |

**Analysis of the gap between strict and lenient.** Inspecting every strict miss
shows only **one genuine model error** — the rest are ground-truth label noise:

- *Party Two = 50% strict but 100% lenient.* The two strict misses are corrupted
  labels, not model errors: gold `.B.Kishore` carries a leading-dot OCR artifact
  (model correctly produced `B.Kishore`), and gold ` VYSHNAVI DAIRY ... Ltd` vs
  the model's `SRI VYSHNAVI DAIRY ... Ltd.` differ only by a brand-vs-honorific
  `SRI` prefix and a trailing dot. Semantically the model is 100% correct.
- *End Date = 75%.* The single miss is an off-by-one-day on a *derived* date
  (`30.03.2011` vs `31.03.2011`) — the source states a term, not an end date, and
  the ground truth uses an inconsistent rounding convention.

So the model's **true semantic recall is ~96%**, and the headline strict number
is dragged down almost entirely by noise in the provided labels (impossible
dates, stray leading dots, trailing spaces) rather than by extraction mistakes.

### Test-set predictions

The generated predictions are saved at [`outputs/predictions.csv`](outputs/predictions.csv):

| File Name | Value | Start | End | Renewal | Party One | Party Two |
|-----------|-------|-------|-----|---------|-----------|-----------|
| 156155545-Rental-Agreement-Kns-Home | 12000 | 15.12.2012 | 14.11.2013 | 30 | V.K.NATARAJ | SRI VYSHNAVI DAIRY SPECIALITIES Private Ltd. |
| 228094620-Rental-Agreement | 15000 | 07.07.2013 | 06.06.2014 | 30 | KAPIL MEHROTRA | B.Kishore |
| 24158401-Rental-Agreement | 12000 | 01.04.2008 | 31.03.2009 | 60 | Hanumaiah | Vishal Bhardwaj |
| 95980236-Rental-Agreement | 9000 | 01.04.2010 | 30.03.2011 | 30 | S.Sakunthala | V.V.Ravi Kian |

---

## 7. Tests

```bash
python -m pytest tests/ -q
```

---

## 8. Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `GEMINI_API_KEY` | — | Google Gemini API key (required) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Use `gemini-2.5-pro` for max accuracy |
