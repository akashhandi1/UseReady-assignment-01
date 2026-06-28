"""Generate sample rental-agreement files to test the /extract endpoint.

Produces:
  * sample_agreements/rental_agreement.docx  (text path)
  * sample_agreements/rental_agreement.png   (image/scanned path)

Both contain the same agreement so the six extracted fields should match:
  agreement_value      = 9000
  agreement_start_date = 01.04.2010
  agreement_end_date   = 28.02.2011   (11-month term)
  renewal_notice_days  = 30           ("one month")
  party_one (lessor)   = Rajesh Kumar Sharma
  party_two (lessee)   = Anita Desai
"""
from pathlib import Path

from docx import Document
from PIL import Image, ImageDraw, ImageFont

OUT = Path("sample_agreements")
OUT.mkdir(exist_ok=True)

LINES = [
    "RENTAL AGREEMENT",
    "",
    "This Rental Agreement is made and executed on this 1st day of April, 2010",
    "at Pune.",
    "",
    "BETWEEN",
    "",
    "Mr. Rajesh Kumar Sharma, residing at 12 MG Road, Pune, hereinafter",
    "referred to as the LESSOR / OWNER (Party One).",
    "",
    "AND",
    "",
    "Ms. Anita Desai, residing at 45 FC Road, Pune, hereinafter referred to",
    "as the LESSEE / TENANT (Party Two).",
    "",
    "TERMS AND CONDITIONS",
    "",
    "1. The Lessor hereby agrees to let out the premises to the Lessee for a",
    "   period of 11 (eleven) months commencing from 01.04.2010.",
    "",
    "2. The monthly rent payable by the Lessee to the Lessor shall be",
    "   Rs. 9,000/- (Rupees Nine Thousand Only) per month.",
    "",
    "3. Either party intending to terminate or renew this agreement shall give",
    "   one month prior written notice to the other party.",
    "",
    "4. The agreement shall remain in force until the end of the term.",
    "",
    "IN WITNESS WHEREOF the parties have set their hands on the date first",
    "above written.",
    "",
    "LESSOR: Rajesh Kumar Sharma            LESSEE: Anita Desai",
]


def make_docx() -> Path:
    doc = Document()
    for line in LINES:
        doc.add_paragraph(line)
    path = OUT / "rental_agreement.docx"
    doc.save(str(path))
    return path


def make_png() -> Path:
    # A4-ish portrait canvas, white background to mimic a scanned page.
    W, H = 1000, 1300
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    # Try a real TrueType font for legibility; fall back to bitmap default.
    font = title = None
    for name in ("arial.ttf", "DejaVuSans.ttf", "calibri.ttf"):
        try:
            font = ImageFont.truetype(name, 22)
            title = ImageFont.truetype(name, 30)
            break
        except OSError:
            continue
    if font is None:
        font = title = ImageFont.load_default()

    x, y = 60, 50
    for line in LINES:
        f = title if line == "RENTAL AGREEMENT" else font
        draw.text((x, y), line, fill="black", font=f)
        y += 38

    path = OUT / "rental_agreement.png"
    img.save(str(path))
    return path


if __name__ == "__main__":
    d = make_docx()
    p = make_png()
    print(f"Wrote {d.resolve()}")
    print(f"Wrote {p.resolve()}")
