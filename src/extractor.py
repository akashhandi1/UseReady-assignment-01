"""The extraction engine: Gemini multimodal with structured JSON output.

Design is provider-agnostic (``BaseExtractor``) so an offline backend could be
swapped in later, but the shipped default is Google Gemini.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from . import config
from .ingest import DocumentInput, ocr_image
from .normalize import normalize_result
from .prompts import SYSTEM_PROMPT, build_fewshot_block
from .schema import ExtractionResult


class BaseExtractor(ABC):
    @abstractmethod
    def extract(self, doc: DocumentInput) -> dict:
        """Return a normalized dict of the six fields for one document."""


class GeminiExtractor(BaseExtractor):
    def __init__(self, model: str | None = None, api_key: str | None = None):
        from google import genai

        key = api_key or config.GEMINI_API_KEY
        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Copy .env.example to .env and add "
                "your key (https://aistudio.google.com/apikey)."
            )
        self.client = genai.Client(api_key=key)
        self.model = model or config.GEMINI_MODEL
        self._fewshot = build_fewshot_block()

    def _build_contents(self, doc: DocumentInput) -> list:
        from google.genai import types

        instruction = (
            f"{self._fewshot}"
            "Now extract the six fields from the following document.\n\n"
        )
        contents: list = []
        if doc.modality == "text":
            contents.append(instruction + "--- DOCUMENT ---\n" + (doc.text or ""))
        else:  # image: send the picture directly to the multimodal model
            contents.append(instruction + "--- DOCUMENT (image below) ---")
            contents.append(
                types.Part.from_bytes(
                    data=doc.image_bytes, mime_type=doc.mime_type or "image/png"
                )
            )
        return contents

    def extract(self, doc: DocumentInput) -> dict:
        from google.genai import types

        config_obj = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=ExtractionResult,
            temperature=0.0,
        )
        response = self.client.models.generate_content(
            model=self.model,
            contents=self._build_contents(doc),
            config=config_obj,
        )
        parsed: ExtractionResult = response.parsed
        raw = parsed.model_dump() if parsed else {}
        return normalize_result(raw)


def get_extractor() -> BaseExtractor:
    """Factory for the default extractor."""
    return GeminiExtractor()
