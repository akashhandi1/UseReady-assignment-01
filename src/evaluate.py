"""Evaluation harness: per-field Recall, reproducing the assignment metric.

  Recall(field) = exact_matches / (exact_matches + misses)

We report TWO numbers per field:
  * strict  -> exact string match (the assignment's headline metric)
  * lenient -> casefold + whitespace-collapsed + date-equivalent (diagnostic,
               isolates true model errors from ground-truth label noise)

Usage:
    python -m src.evaluate --gold data/test.csv --pred outputs/predictions.csv
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

from . import config

FIELDS = config.CSV_HEADERS[1:]  # everything except "File Name"


def _canon(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip()


def _lenient(field: str, s: str) -> str:
    s = _canon(s).casefold()
    if "date" in field.lower():
        parts = [p for p in re.split(r"[.\-/\s]+", s) if p]
        if len(parts) == 3:
            try:
                d, m, y = (int(p) for p in parts)
                if y < 100:
                    y += 2000
                return f"{d:02d}.{m:02d}.{y:04d}"
            except ValueError:
                pass
    if field in ("Aggrement Value", "Renewal Notice (Days)"):
        digits = re.sub(r"[^\d]", "", s)
        return digits
    if field in ("Party One", "Party Two"):
        # strip honorifics + non-alphanumerics for a semantic name comparison
        s = re.sub(r"\b(mr|mrs|ms|m/s|sri|shri|smt|dr|thiru)\b\.?", "", s)
        s = re.sub(r"[^a-z0-9]", "", s)
        return s
    return s


def evaluate(gold_csv: str | Path, pred_csv: str | Path) -> dict:
    gold = pd.read_csv(gold_csv, dtype=str).fillna("")
    pred = pd.read_csv(pred_csv, dtype=str).fillna("")

    gold["__key"] = gold["File Name"].map(_canon)
    pred["__key"] = pred["File Name"].map(_canon)
    pred_by_key = {row["__key"]: row for _, row in pred.iterrows()}

    strict_hits = {f: 0 for f in FIELDS}
    lenient_hits = {f: 0 for f in FIELDS}
    total = 0
    details: list[dict] = []

    for _, g in gold.iterrows():
        total += 1
        p = pred_by_key.get(g["__key"])
        row_detail = {"File Name": g["File Name"]}
        for f in FIELDS:
            gval = g.get(f, "")
            pval = p.get(f, "") if p is not None else ""
            strict_ok = _canon(gval) == _canon(pval)
            lenient_ok = _lenient(f, gval) == _lenient(f, pval)
            strict_hits[f] += int(strict_ok)
            lenient_hits[f] += int(lenient_ok)
            mark = "OK " if strict_ok else ("~  " if lenient_ok else "X  ")
            row_detail[f] = f"{mark} pred='{pval}' gold='{gval}'"
        details.append(row_detail)

    strict_recall = {f: strict_hits[f] / total for f in FIELDS}
    lenient_recall = {f: lenient_hits[f] / total for f in FIELDS}
    return {
        "total": total,
        "strict_recall": strict_recall,
        "lenient_recall": lenient_recall,
        "strict_macro": sum(strict_recall.values()) / len(FIELDS),
        "lenient_macro": sum(lenient_recall.values()) / len(FIELDS),
        "details": details,
    }


def print_report(res: dict) -> None:
    print(f"\nEvaluated {res['total']} documents.\n")
    print(f"{'Field':<24}{'Strict Recall':>16}{'Lenient Recall':>18}")
    print("-" * 58)
    for f in FIELDS:
        print(f"{f:<24}{res['strict_recall'][f]:>15.2%}{res['lenient_recall'][f]:>18.2%}")
    print("-" * 58)
    print(f"{'MACRO AVERAGE':<24}{res['strict_macro']:>15.2%}{res['lenient_macro']:>18.2%}")

    print("\nPer-document detail (OK exact | ~ lenient-only | X miss):")
    for d in res["details"]:
        print(f"\n  {d['File Name']}")
        for f in FIELDS:
            print(f"    {f:<24} {d[f]}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Per-field recall evaluation.")
    ap.add_argument("--gold", default=str(config.TEST_CSV))
    ap.add_argument("--pred", default=str(config.OUTPUT_DIR / "predictions.csv"))
    args = ap.parse_args()
    res = evaluate(args.gold, args.pred)
    print_report(res)


if __name__ == "__main__":
    main()
