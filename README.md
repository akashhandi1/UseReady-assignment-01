# Rental Agreement Metadata Extraction

A system that reads a rental/lease agreement and pulls out six metadata fields.
It works on any template, and accepts either a `.docx` file or a scanned `.png`
image.

The six fields:

| Field | Description |
|-------|-------------|
| Agreement Value | Monthly rent, as an integer |
| Agreement Start Date | `DD.MM.YYYY` |
| Agreement End Date | `DD.MM.YYYY` |
| Renewal Notice (Days) | Notice period, in days |
| Party One | Lessor / owner |
| Party Two | Lessee / tenant |


## 1. Solution Approach

### The core idea

A multimodal Large Language Model (Google Gemini) does the actual extraction.
There is no rule-based, RegEx, or keyword-matching logic that decides what a
value is. This is a deliberate choice, and it is also the constraint the
assignment sets.

### Why an LLM, and not RegEx / NER / a QA model

Looking at the data closely, the six fields are not all written directly in the
documents. Some of them have to be worked out:

1. **The end date is usually not in the document.** Most agreements state a
   *term*, like "11 months" or "1 year", and a start date. The end date in the
   ground truth is `start date + term`. Some of the labels are even calendar
   dates that don't exist (for example `31.02.2011`), because that is what the
   arithmetic produced. You cannot match this with a pattern; you have to
   reason about it.

2. **The renewal notice needs a unit conversion.** The text might say "one
   month prior notice", but the expected answer is `30`. Again, this is
   reasoning, not pattern matching.

3. **Every document uses a different template.** A solution that has to work on
   any layout is much easier to build with a model that reads for meaning than
   with code written against specific templates.

A RegEx or NER pipeline would need hand-written rules for exactly these cases,
which is what the assignment rules out. A model that understands the text
handles all three naturally.

### How a document flows through the system

1. **Ingestion.** The file extension decides the path. A `.docx` is parsed into
   plain text (paragraphs and tables) with `python-docx`. A `.png` is read as
   raw image bytes.

2. **Extraction.** The text or the image is sent to Gemini together with:
   - a system prompt that defines each field and the reasoning rules (compute
     the end date from the term, convert months to days, strip honorifics from
     names, and so on);
   - a few worked examples taken automatically from the training set, so the
     model sees the expected input/output shape;
   - a Pydantic schema passed as the response schema, which forces the model to
     reply with valid JSON containing exactly the six fields.

   Images go straight to the vision model. There is no OCR step in the default
   path, so there is no OCR error to clean up afterwards.

3. **Normalization.** A small formatting layer (`src/normalize.py`) cleans up
   the model's answer so it matches the CSV conventions: zero-pad dates to
   `DD.MM.YYYY`, strip `Rs`/commas from the rent, trim whitespace from names.
   This layer only reformats a value the model already chose. It never reads the
   document or decides a value itself, so the extraction stays fully
   model-driven.

4. **Output.** The result is written to `predictions.csv` (batch mode) or
   returned as JSON (the REST API).

### A note on "no rule-based extraction"

The only non-model code that touches the values is the normalization layer, and
all it does is reformat. It does not search the document, and it does not pick a
value. The decision of *what* each field is always comes from the model.

### Data decisions worth calling out

- The few-shot examples are loaded from the training set at runtime
  (`src/prompts.py`), not hard-coded. The file `24158401` is excluded from the
  examples because it also appears in the test set, which would be data leakage.
  The unlabeled file `46239065` is excluded too.
- Images are read directly by the vision model. `pytesseract` is included only
  as an offline fallback and is not used in the default flow.
- The `.pdf.docx` files in the test set are ordinary text-based `.docx` files
  (checked by hand), so they go through the docx path.


## 2. Architecture

```
                      input file (.docx or .png)
                                 |
                                 v
                    +------------------------+
                    |  ingest.py             |
                    |  route by extension    |
                    +------------------------+
                       |                   |
              .docx    |                   |   .png
                       v                   v
              python-docx text       raw image bytes
                       \                   /
                        \                 /
                         v               v
                    +------------------------+
                    |  extractor.py          |
                    |  Gemini call with:     |
                    |   - system prompt      |
                    |   - few-shot examples  |
                    |   - JSON schema        |
                    +------------------------+
                                 |
                                 v
                    +------------------------+
                    |  normalize.py          |
                    |  format to CSV style   |
                    +------------------------+
                                 |
              +------------------+------------------+
              |                                     |
              v                                     v
        predict.py                              api.py
        predictions.csv                         JSON response
```

### What each file does

```
assignment-1/
  README.md            this file
  PROJECT_PLAN.md      longer design notes and the reasoning behind each choice
  requirements.txt
  .env.example         copy to .env and add your GEMINI_API_KEY
  data/                the provided dataset (train/, test/, and the csvs)
  src/
    config.py          paths, CSV headers, model config
    schema.py          the Pydantic output schema (the six fields)
    ingest.py          file-type routing and docx/png loading
    prompts.py         system prompt and few-shot examples from the train set
    extractor.py       the Gemini extraction engine
    normalize.py       output formatting
    predict.py         batch runner that writes predictions.csv
    evaluate.py        per-field recall (strict and lenient)
    api.py             the FastAPI service
  tests/
    test_normalize.py  unit tests for the formatting layer
  outputs/
    predictions.csv    the generated test-set predictions
```

A few design points behind the structure:

- **`extractor.py` is written against a `BaseExtractor` interface.** Gemini is
  the only backend today, but a different model (or an offline one) can be added
  without touching the rest of the pipeline.
- **`schema.py` is the single source of truth for the output shape.** It is
  handed to the model as the response schema, so the model is forced to return
  exactly those fields rather than free text we have to parse.
- **Ingestion, extraction, normalization, and evaluation are separate modules.**
  Each one is small and does a single job, so they can be tested and changed on
  their own.


## 3. Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Add your Gemini API key
cp .env.example .env          # on Windows: copy .env.example .env
# then edit .env and set GEMINI_API_KEY=...
# you can get a free key at https://aistudio.google.com/apikey
```

You do not need Tesseract installed. Images go straight to Gemini; Tesseract is
only there for an offline variant.


## 4. Reproduce the Predictions

```bash
# Generate predictions for the test set
python -m src.predict --input data/test --output outputs/predictions.csv

# Score them
python -m src.evaluate --gold data/test.csv --pred outputs/predictions.csv
```

`predict` writes `outputs/predictions.csv` using the exact ground-truth headers.
`evaluate` prints a per-field recall table and a per-document breakdown.


## 5. REST API

```bash
uvicorn src.api:app --reload
# open http://127.0.0.1:8000/docs for the interactive Swagger UI
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


## 6. Evaluation

The metric from the assignment is per-field recall:

```
Recall(field) = exact_matches / (exact_matches + misses)
```

`src/evaluate.py` reports two numbers per field:

- **Strict** is an exact string match. This is the assignment's official metric.
- **Lenient** ignores case, whitespace, and date-equivalence. It is a diagnostic
  to separate real model errors from label noise in the provided CSVs (invalid
  dates, trailing spaces, and so on).

### Test-set recall

Model `gemini-2.5-flash`, temperature 0, on the four documents in `data/test/`.

| Field | Strict Recall | Lenient Recall |
|-------|---------------|----------------|
| Aggrement Value | 100.00% | 100.00% |
| Aggrement Start Date | 100.00% | 100.00% |
| Aggrement End Date | 75.00% | 75.00% |
| Renewal Notice (Days) | 100.00% | 100.00% |
| Party One | 100.00% | 100.00% |
| Party Two | 50.00% | 100.00% |
| Macro average | 87.50% | 95.83% |

Looking at the strict misses one by one, only one of them is an actual model
error. The rest are noise in the ground-truth labels:

- **Party Two, 50% strict but 100% lenient.** Both strict misses are bad labels.
  The gold value `.B.Kishore` has a stray leading dot from OCR (the model
  correctly returned `B.Kishore`), and the gold ` VYSHNAVI DAIRY ... Ltd`
  differs from the model's `SRI VYSHNAVI DAIRY ... Ltd.` only by a `SRI` prefix
  and a trailing dot. The model is right in both cases.
- **End Date, 75%.** The single miss is off by one day on a derived date
  (`30.03.2011` vs `31.03.2011`). The document gives a term, not an end date, and
  the ground truth rounds it inconsistently.

So the real semantic recall is around 96%. The headline strict number is pulled
down almost entirely by label noise, not by extraction mistakes.

### Test-set predictions

The predictions are saved at
[`outputs/predictions.csv`](outputs/predictions.csv):

| File Name | Value | Start | End | Renewal | Party One | Party Two |
|-----------|-------|-------|-----|---------|-----------|-----------|
| 156155545-Rental-Agreement-Kns-Home | 12000 | 15.12.2012 | 14.11.2013 | 30 | V.K.NATARAJ | SRI VYSHNAVI DAIRY SPECIALITIES Private Ltd. |
| 228094620-Rental-Agreement | 15000 | 07.07.2013 | 06.06.2014 | 30 | KAPIL MEHROTRA | B.Kishore |
| 24158401-Rental-Agreement | 12000 | 01.04.2008 | 31.03.2009 | 60 | Hanumaiah | Vishal Bhardwaj |
| 95980236-Rental-Agreement | 9000 | 01.04.2010 | 30.03.2011 | 30 | S.Sakunthala | V.V.Ravi Kian |


## 7. Tests

```bash
python -m pytest tests/ -q
```


## 8. Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `GEMINI_API_KEY` | (none) | Google Gemini API key (required) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Use `gemini-2.5-pro` for higher accuracy |
