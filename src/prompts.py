"""System prompt + few-shot exemplars mined from the train set.

The exemplars are loaded dynamically from ``train.csv`` + the train documents so
nothing is hand-coded. We deliberately use text-based (.docx) exemplars and
exclude any file that leaks into the test set (24158401).
"""
from __future__ import annotations

import pandas as pd

from . import config
from .ingest import load_document

SYSTEM_PROMPT = """\
You are an expert contract-analysis model. You read a single rental/lease \
agreement (provided as text or as a scanned image) and extract six metadata \
fields. The documents come in many different templates and layouts, so reason \
from meaning, not from fixed positions.

Extract exactly these fields:

1. Agreement Value  -> the MONTHLY rent amount, as digits only (no 'Rs', no \
commas, no '/-', no words). If both digits and words disagree, trust the digits.
2. Agreement Start Date -> the commencement date, formatted DD.MM.YYYY.
3. Agreement End Date -> formatted DD.MM.YYYY. Documents usually state a TERM \
(e.g. "11 months" or "1 year") rather than an explicit end date; in that case \
compute the end date as start_date + term.
4. Renewal Notice (Days) -> the notice period before vacating/renewal, in DAYS. \
Convert worded units to days: "one month" = 30, "two months" = 60, "three \
months" = 90, "15 days" = 15.
5. Party One -> the LESSOR / OWNER / landlord (who owns and rents out the property).
6. Party Two -> the LESSEE / TENANT (who rents the property).

Party-name rules (important):
- Give the NAME ONLY. Do NOT include honorific prefixes such as Mr., Mrs., Ms., \
M/s, Sri, Shri, Smt., Dr., Thiru.
- Do NOT include parentage or relationship clauses (S/o, D/o, W/o, "son of", \
"aged about", addresses). Stop at the person's / entity's name.
- For a company, keep its full legal name (e.g. "... Private Ltd") but drop any \
leading honorific and any trailing punctuation.
- Preserve the spelling and spacing of the name exactly as written otherwise.

General rules:
- Return an empty string for any field you genuinely cannot find. Never invent values.
- Output must conform to the provided JSON schema.
"""

# Train files used as worked examples (text-based, verifiable, term variety).
# 24158401 is intentionally excluded (it also appears in the test set).
EXEMPLAR_STEMS = [
    "6683127-House-Rental-Contract-GERALDINE-GALINATO-v2-Page-1",  # 1-year term
    "50070534-RENTAL-AGREEMENT",                                    # 11-month term
    "47854715-RENTAL-AGREEMENT",                                    # derived end date
]


def _train_labels() -> dict[str, dict]:
    df = pd.read_csv(config.TRAIN_CSV, dtype=str).fillna("")
    return {row["File Name"].strip(): row for _, row in df.iterrows()}


def build_fewshot_block() -> str:
    """Render the few-shot exemplars as a text block for the prompt."""
    labels = _train_labels()
    blocks: list[str] = []

    for stem in EXEMPLAR_STEMS:
        path = config.TRAIN_DIR / f"{stem}.docx"
        if not path.exists() or stem not in labels:
            continue
        doc = load_document(path)
        row = labels[stem]
        answer = {
            "agreement_value": row["Aggrement Value"].strip(),
            "agreement_start_date": row["Aggrement Start Date"].strip(),
            "agreement_end_date": row["Aggrement End Date"].strip(),
            "renewal_notice_days": row["Renewal Notice (Days)"].strip(),
            "party_one": row["Party One"].strip(),
            "party_two": row["Party Two"].strip(),
        }
        import json

        # Truncate very long exemplar bodies to keep the prompt compact.
        body = (doc.text or "")[:2500]
        blocks.append(
            f"--- EXAMPLE DOCUMENT ---\n{body}\n\n"
            f"--- CORRECT EXTRACTION ---\n{json.dumps(answer, ensure_ascii=False)}"
        )

    if not blocks:
        return ""
    return (
        "Here are worked examples showing the expected reasoning and output:\n\n"
        + "\n\n".join(blocks)
        + "\n\n"
    )
