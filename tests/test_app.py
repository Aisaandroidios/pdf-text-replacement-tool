from io import BytesIO

import fitz
import pytest
from fastapi.testclient import TestClient

import server.app as app_module
from server.app import app
from server.ocr_service import tesseract_available


def make_pdf_with_text(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=300, height=160)
    page.insert_text((40, 80), text, fontsize=14)
    return doc.tobytes()


def make_png_with_text(
    text: str,
    fill: tuple[int, int, int] = (0, 0, 0),
    background: tuple[int, int, int] = (255, 255, 255),
) -> bytes:
    pillow = pytest.importorskip("PIL.Image")
    image_draw = pytest.importorskip("PIL.ImageDraw")
    image_font = pytest.importorskip("PIL.ImageFont")

    image = pillow.new("RGB", (900, 260), background)
    draw = image_draw.Draw(image)
    font = image_font.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 72)
    draw.text((70, 80), text, fill=fill, font=font)

    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_index_serves_tool_ui():
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "PDF 信息替换工具" in response.text
    assert "替换所有相同文字" in response.text
    assert "image/png" in response.text
    assert "选择 PDF / 图片" in response.text
    assert 'id="exportFormat"' in response.text
    assert "导出格式" in response.text


def test_extract_endpoint_returns_document_id_and_text():
    client = TestClient(app)

    response = client.post(
        "/api/extract",
        files={"file": ("sample.pdf", make_pdf_with_text("Invoice: 1001"), "application/pdf")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["document_id"]
    assert payload["page_count"] == 1
    assert payload["pages"][0]["items"][0]["text"] == "Invoice: 1001"


def test_extract_endpoint_accepts_image_upload_and_stores_as_pdf():
    client = TestClient(app)

    response = client.post(
        "/api/extract",
        files={"file": ("sample.png", make_png_with_text("IMAGE CODE 123"), "image/png")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["document_id"]
    assert payload["filename"] == "sample.png"
    assert payload["preview_filename"] == "sample.pdf"
    assert payload["source_type"] == "image"
    assert payload["recommended_export_format"] == "source"
    assert payload["export_options"] == [
        {"value": "source", "label": "保持原图格式 PNG"},
        {"value": "pdf", "label": "导出 PDF"},
    ]
    document_response = client.get(f"/api/document/{payload['document_id']}")
    assert document_response.status_code == 200
    assert document_response.headers["content-type"] == "application/pdf"


def test_extract_endpoint_reads_image_text_with_ocr_when_available():
    if not tesseract_available():
        pytest.skip("Tesseract OCR is not installed")

    client = TestClient(app)

    response = client.post(
        "/api/extract",
        files={"file": ("sample.png", make_png_with_text("IMAGE CODE 123"), "image/png")},
    )

    assert response.status_code == 200
    payload = response.json()
    items = [item for page in payload["pages"] for item in page["items"]]
    assert payload["ocr_available"] is True
    assert any(item["source"] == "ocr" and "IMAGE CODE 123" in item["text"] for item in items)


def test_export_endpoint_returns_modified_pdf():
    client = TestClient(app)
    extract_response = client.post(
        "/api/extract",
        files={"file": ("sample.pdf", make_pdf_with_text("Invoice: 1001"), "application/pdf")},
    )
    extracted = extract_response.json()
    target = extracted["pages"][0]["items"][0]

    export_response = client.post(
        "/api/export",
        json={
            "document_id": extracted["document_id"],
            "replacements": [
                {
                    "page_index": target["page_index"],
                    "item_id": target["id"],
                    "bbox": target["bbox"],
                    "old_text": target["text"],
                    "new_text": "Invoice: 2002",
                }
            ],
        },
    )

    assert export_response.status_code == 200
    assert export_response.headers["content-type"] == "application/pdf"
    output_text = "\n".join(
        page.get_text() for page in fitz.open(stream=export_response.content, filetype="pdf")
    )
    assert "Invoice: 2002" in output_text
    assert "Invoice: 1001" not in output_text


def test_export_save_endpoint_writes_modified_pdf_to_downloads(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "DOWNLOADS_DIR", tmp_path)
    client = TestClient(app)
    extract_response = client.post(
        "/api/extract",
        files={"file": ("sample.pdf", make_pdf_with_text("Invoice: 1001"), "application/pdf")},
    )
    extracted = extract_response.json()
    target = extracted["pages"][0]["items"][0]

    export_response = client.post(
        "/api/export-save",
        json={
            "document_id": extracted["document_id"],
            "replacements": [
                {
                    "page_index": target["page_index"],
                    "item_id": target["id"],
                    "bbox": target["bbox"],
                    "old_text": target["text"],
                    "new_text": "Invoice: 2002",
                    "font_size": target["font_size"],
                    "font": target["font"],
                    "color": target["color"],
                    "origin": target["origin"],
                }
            ],
        },
    )

    assert export_response.status_code == 200
    payload = export_response.json()
    saved_path = tmp_path / payload["filename"]
    assert payload["saved_path"] == str(saved_path)
    assert saved_path.exists()
    output_text = "\n".join(page.get_text() for page in fitz.open(saved_path))
    assert "Invoice: 2002" in output_text
    assert "Invoice: 1001" not in output_text


def test_export_save_endpoint_keeps_image_upload_as_image_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "DOWNLOADS_DIR", tmp_path)
    client = TestClient(app)
    extract_response = client.post(
        "/api/extract",
        files={"file": ("sample.png", make_png_with_text("IMAGE CODE 123"), "image/png")},
    )
    extracted = extract_response.json()
    target = next(
        item
        for page in extracted["pages"]
        for item in page["items"]
        if "IMAGE CODE 123" in item["text"]
    )

    export_response = client.post(
        "/api/export-save",
        json={
            "document_id": extracted["document_id"],
            "filename": extracted["filename"],
            "replacements": [
                {
                    "page_index": target["page_index"],
                    "item_id": target["id"],
                    "bbox": target["bbox"],
                    "old_text": target["text"],
                    "new_text": "IMAGE DONE 999",
                    "font_size": target["font_size"],
                    "font": target["font"],
                    "color": target["color"],
                    "origin": target["origin"],
                }
            ],
        },
    )

    assert export_response.status_code == 200
    payload = export_response.json()
    saved_path = tmp_path / payload["filename"]
    assert saved_path.suffix == ".png"
    assert payload["output_format"] == "source"
    assert payload["media_type"] == "image/png"
    assert payload["saved_path"] == str(saved_path)
    assert saved_path.exists()
    assert saved_path.read_bytes().startswith(b"\x89PNG")


def test_export_save_endpoint_can_export_image_upload_as_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "DOWNLOADS_DIR", tmp_path)
    client = TestClient(app)
    extract_response = client.post(
        "/api/extract",
        files={"file": ("sample.png", make_png_with_text("IMAGE CODE 123"), "image/png")},
    )
    extracted = extract_response.json()
    target = next(
        item
        for page in extracted["pages"]
        for item in page["items"]
        if "IMAGE CODE 123" in item["text"]
    )

    export_response = client.post(
        "/api/export-save",
        json={
            "document_id": extracted["document_id"],
            "filename": extracted["filename"],
            "output_format": "pdf",
            "replacements": [
                {
                    "page_index": target["page_index"],
                    "item_id": target["id"],
                    "bbox": target["bbox"],
                    "old_text": target["text"],
                    "new_text": "IMAGE DONE 999",
                    "font_size": target["font_size"],
                    "font": target["font"],
                    "color": target["color"],
                    "origin": target["origin"],
                }
            ],
        },
    )

    assert export_response.status_code == 200
    payload = export_response.json()
    saved_path = tmp_path / payload["filename"]
    assert saved_path.suffix == ".pdf"
    assert payload["output_format"] == "pdf"
    assert payload["media_type"] == "application/pdf"
    assert saved_path.exists()
    assert saved_path.read_bytes().startswith(b"%PDF")


def test_export_save_endpoint_preserves_image_size_and_detected_text_color(
    tmp_path, monkeypatch
):
    if not tesseract_available():
        pytest.skip("Tesseract OCR is not installed")

    image_module = pytest.importorskip("PIL.Image")
    monkeypatch.setattr(app_module, "DOWNLOADS_DIR", tmp_path)
    client = TestClient(app)
    extract_response = client.post(
        "/api/extract",
        files={
            "file": (
                "style-sample.png",
                make_png_with_text(
                    "STYLE CODE 123",
                    fill=(14, 72, 164),
                    background=(244, 246, 238),
                ),
                "image/png",
            )
        },
    )
    extracted = extract_response.json()
    target = next(
        item
        for page in extracted["pages"]
        for item in page["items"]
        if "STYLE CODE 123" in item["text"]
    )

    export_response = client.post(
        "/api/export-save",
        json={
            "document_id": extracted["document_id"],
            "filename": extracted["filename"],
            "replacements": [
                {
                    "page_index": target["page_index"],
                    "item_id": target["id"],
                    "bbox": target["bbox"],
                    "old_text": target["text"],
                    "new_text": "STYLE CODE 999",
                    "font_size": target["font_size"],
                    "font": target["font"],
                    "color": target["color"],
                    "origin": target["origin"],
                }
            ],
        },
    )

    assert export_response.status_code == 200
    saved_path = tmp_path / export_response.json()["filename"]
    assert saved_path.suffix == ".png"

    edited = image_module.open(saved_path).convert("RGB")
    assert edited.size == (900, 260)
    pixels = list(edited.getdata())
    blueish_pixels = [
        pixel for pixel in pixels if pixel[0] < 80 and 45 <= pixel[1] <= 120 and pixel[2] > 120
    ]
    assert len(blueish_pixels) > 100
