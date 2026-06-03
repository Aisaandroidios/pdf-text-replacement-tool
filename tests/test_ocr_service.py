from io import BytesIO

import fitz
import pytest

from server.ocr_service import ocr_data_to_items, overlaps_existing_text
from server.ocr_service import tesseract_available
from server.pdf_service import extract_pdf_text


def make_image_only_pdf(text: str) -> bytes:
    pillow = pytest.importorskip("PIL.Image")
    image_draw = pytest.importorskip("PIL.ImageDraw")
    image_font = pytest.importorskip("PIL.ImageFont")

    image = pillow.new("RGB", (900, 260), "white")
    draw = image_draw.Draw(image)
    font = image_font.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 72)
    draw.text((70, 80), text, fill="black", font=font)

    stream = BytesIO()
    image.save(stream, format="PNG")
    doc = fitz.open()
    page = doc.new_page(width=450, height=130)
    page.insert_image(page.rect, stream=stream.getvalue())
    return doc.tobytes()


def test_ocr_data_to_items_groups_words_by_line_and_converts_coordinates():
    page = fitz.Rect(0, 0, 200, 100)
    data = {
        "level": [5, 5, 5],
        "block_num": [1, 1, 1],
        "par_num": [1, 1, 1],
        "line_num": [1, 1, 2],
        "word_num": [1, 2, 1],
        "text": ["Invoice", "123", "Paid"],
        "conf": ["91", "90", "95"],
        "left": [20, 95, 20],
        "top": [30, 30, 70],
        "width": [70, 40, 45],
        "height": [20, 20, 18],
    }

    items = ocr_data_to_items(data, page_index=0, page_rect=page, scale=2)

    assert items == [
        {
            "id": "p0-ocr-b1-p1-l1",
            "page_index": 0,
            "page_number": 1,
            "text": "Invoice 123",
            "bbox": [10.0, 15.0, 67.5, 25.0],
            "origin": [10.0, 25.0],
            "font_size": 7.2,
            "font": "helv",
            "color": "#000000",
            "source": "ocr",
        },
        {
            "id": "p0-ocr-b1-p1-l2",
            "page_index": 0,
            "page_number": 1,
            "text": "Paid",
            "bbox": [10.0, 35.0, 32.5, 44.0],
            "origin": [10.0, 44.0],
            "font_size": 6.48,
            "font": "helv",
            "color": "#000000",
            "source": "ocr",
        },
    ]


def test_overlaps_existing_text_filters_ocr_duplicates():
    ocr_item = {"bbox": [10.0, 15.0, 67.5, 25.0]}
    selectable_items = [{"bbox": [9.0, 14.0, 68.0, 26.0], "text": "Invoice 123"}]

    assert overlaps_existing_text(ocr_item, selectable_items)
    assert not overlaps_existing_text({"bbox": [100.0, 70.0, 130.0, 90.0]}, selectable_items)


def test_extract_pdf_text_reads_text_inside_images_when_ocr_is_available():
    if not tesseract_available():
        pytest.skip("Tesseract OCR is not installed")

    result = extract_pdf_text(make_image_only_pdf("OCR CODE 123"))
    items = [item for page in result["pages"] for item in page["items"]]

    assert result["ocr_available"] is True
    assert any(item["source"] == "ocr" and "OCR CODE 123" in item["text"] for item in items)
