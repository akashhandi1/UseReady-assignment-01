"""Pydantic schema for the structured extraction output.

This schema is handed to Gemini via ``response_schema`` so the model is forced
to return the six fields (plus a short rationale used only for debugging).
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractionResult(BaseModel):
    """The six metadata fields extracted from a rental agreement."""

    agreement_value: str = Field(
        description=(
            "Monthly rent amount as a plain integer string, digits only "
            "(strip 'Rs', commas, '/-', and any words). Example: '9000'. "
            "Empty string if not found."
        )
    )
    agreement_start_date: str = Field(
        description=(
            "Start/commencement date of the agreement in DD.MM.YYYY format. "
            "Example: '01.04.2010'. Empty string if not found."
        )
    )
    agreement_end_date: str = Field(
        description=(
            "End date in DD.MM.YYYY format. If the document only gives a term "
            "(e.g. '11 months' or '1 year'), compute end = start + term. "
            "Empty string if it cannot be determined."
        )
    )
    renewal_notice_days: str = Field(
        description=(
            "Notice period required before renewal/vacating, expressed as a "
            "number of DAYS (integer string). Convert units: 'one month' -> "
            "'30', 'two months' -> '60', '15 days' -> '15'. Empty if not found."
        )
    )
    party_one: str = Field(
        description=(
            "The first party: the lessor / owner / landlord (the person who "
            "owns and rents out the premises). Name only. Empty if not found."
        )
    )
    party_two: str = Field(
        description=(
            "The second party: the lessee / tenant (the person renting the "
            "premises). Name only. Empty if not found."
        )
    )
    rationale: str = Field(
        default="",
        description=(
            "Brief note on where each value was found / how end date and "
            "renewal days were derived. For debugging; not part of output."
        ),
    )
