import fitz

from server.pdf_service import Replacement, export_pdf_with_replacements, extract_pdf_text


def make_pdf_with_text(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=300, height=160)
    page.insert_text((40, 80), text, fontsize=14)
    return doc.tobytes()


def make_pdf_with_lines(lines: list[str]) -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=360, height=220)
    for index, line in enumerate(lines):
        page.insert_text((40, 60 + index * 34), line, fontsize=14)
    return doc.tobytes()


def make_pdf_with_styled_text(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=360, height=180)
    page.insert_text((40, 90), text, fontsize=18, fontname="Courier", color=(0, 0.35, 0.9))
    return doc.tobytes()


def test_extract_pdf_text_returns_page_spans():
    result = extract_pdf_text(make_pdf_with_text("Name: Alice"))

    assert result["page_count"] == 1
    assert result["pages"][0]["page_number"] == 1
    assert any("Name: Alice" in item["text"] for item in result["pages"][0]["items"])


def test_extract_pdf_text_skips_ocr_when_all_pages_have_selectable_text(monkeypatch):
    def fail_if_called(doc, pages):
        raise AssertionError("OCR should not run when every page has selectable text")

    monkeypatch.setattr("server.pdf_service.extract_ocr_text", fail_if_called)

    result = extract_pdf_text(make_pdf_with_text("Name: Alice"))

    assert result["ocr_available"] is False
    assert any("Name: Alice" in item["text"] for item in result["pages"][0]["items"])


def test_export_pdf_with_replacements_replaces_selected_text():
    source = make_pdf_with_text("Name: Alice")
    extracted = extract_pdf_text(source)
    target = next(item for item in extracted["pages"][0]["items"] if "Name: Alice" in item["text"])

    output = export_pdf_with_replacements(
        source,
        [
            Replacement(
                page_index=0,
                item_id=target["id"],
                bbox=target["bbox"],
                old_text=target["text"],
                new_text="Name: Bob",
            )
        ],
    )

    output_text = "\n".join(page.get_text() for page in fitz.open(stream=output, filetype="pdf"))
    assert "Name: Bob" in output_text
    assert "Name: Alice" not in output_text


def test_export_pdf_with_replacements_can_replace_all_matching_text_items():
    source = make_pdf_with_lines(["Status: Pending", "Owner: Alice", "Status: Pending"])
    extracted = extract_pdf_text(source)
    targets = [
        item
        for page in extracted["pages"]
        for item in page["items"]
        if item["text"] == "Status: Pending"
    ]

    output = export_pdf_with_replacements(
        source,
        [
            Replacement(
                page_index=target["page_index"],
                item_id=target["id"],
                bbox=target["bbox"],
                old_text=target["text"],
                new_text="Status: Done",
            )
            for target in targets
        ],
    )

    output_text = "\n".join(page.get_text() for page in fitz.open(stream=output, filetype="pdf"))
    assert output_text.count("Status: Done") == 2
    assert "Status: Pending" not in output_text
    assert "Owner: Alice" in output_text


def test_export_pdf_with_replacements_preserves_original_size_and_color():
    source = make_pdf_with_styled_text("Code: 1234")
    extracted = extract_pdf_text(source)
    target = extracted["pages"][0]["items"][0]

    output = export_pdf_with_replacements(
        source,
        [
            Replacement(
                page_index=0,
                item_id=target["id"],
                bbox=target["bbox"],
                old_text=target["text"],
                new_text="Code: 5678",
                font_size=target["font_size"],
                font=target["font"],
                color=target["color"],
                origin=target["origin"],
            )
        ],
    )

    output_page = fitz.open(stream=output, filetype="pdf")[0]
    spans = [
        span
        for block in output_page.get_text("dict")["blocks"]
        for line in block.get("lines", [])
        for span in line.get("spans", [])
        if span["text"] == "Code: 5678"
    ]
    assert len(spans) == 1
    assert spans[0]["size"] == target["font_size"]
    assert spans[0]["color"] == int(target["color"].lstrip("#"), 16)
