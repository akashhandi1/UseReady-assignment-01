"""Batch runner: extract metadata for every document in a folder -> CSV.

Usage:
    python -m src.predict --input data/test --output outputs/predictions.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from . import config
from .extractor import BaseExtractor, get_extractor
from .ingest import list_documents, load_document


def predict_folder(
    input_dir: str | Path,
    output_csv: str | Path,
    extractor: BaseExtractor | None = None,
) -> pd.DataFrame:
    extractor = extractor or get_extractor()
    rows: list[dict] = []

    for path in list_documents(input_dir):
        try:
            doc = load_document(path)
            fields = extractor.extract(doc)
            print(f"[ok]  {doc.file_name}", file=sys.stderr)
        except Exception as exc:  # keep going on per-file failure
            print(f"[err] {path.name}: {exc}", file=sys.stderr)
            doc_name = path.stem
            if doc_name.lower().endswith(".pdf"):
                doc_name = doc_name[:-4]
            empty = {k: "" for k in config.FIELD_TO_HEADER}
            rows.append(_row(doc_name, empty))
            continue
        rows.append(_row(doc.file_name, fields))

    df = pd.DataFrame(rows, columns=config.CSV_HEADERS)
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)
    print(f"\nWrote {len(df)} predictions -> {output_csv}", file=sys.stderr)
    return df


def _row(file_name: str, fields: dict) -> dict:
    row = {"File Name": file_name}
    for key, header in config.FIELD_TO_HEADER.items():
        row[header] = fields.get(key, "")
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract rental-agreement metadata.")
    ap.add_argument("--input", default=str(config.TEST_DIR), help="Folder of documents")
    ap.add_argument(
        "--output",
        default=str(config.OUTPUT_DIR / "predictions.csv"),
        help="Output CSV path",
    )
    args = ap.parse_args()
    predict_folder(args.input, args.output)


if __name__ == "__main__":
    main()
