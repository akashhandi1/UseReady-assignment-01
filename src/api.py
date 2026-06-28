"""FastAPI REST wrapper around the extraction pipeline.

Run:
    uvicorn src.api:app --reload
Then open http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile

from .extractor import get_extractor
from .ingest import load_document

app = FastAPI(
    title="Rental Agreement Metadata Extractor",
    description="Extract 6 metadata fields from a .docx or scanned .png agreement.",
    version="1.0.0",
)

_extractor = None


def _get_extractor():
    global _extractor
    if _extractor is None:
        _extractor = get_extractor()
    return _extractor


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/extract")
async def extract(file: UploadFile = File(...)) -> dict:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".docx", ".png", ".jpg", ".jpeg"}:
        raise HTTPException(400, f"Unsupported file type: {suffix}")

    data = await file.read()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)

    try:
        doc = load_document(tmp_path)
        # keep the uploaded original name, not the temp name
        doc.file_name = Path(file.filename).stem
        fields = _get_extractor().extract(doc)
    except Exception as exc:
        raise HTTPException(500, f"Extraction failed: {exc}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    return {"file_name": file.filename, "fields": fields}
