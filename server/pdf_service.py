from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import fitz

from server.ocr_service import extract_ocr_text


MIN_FONT_SIZE = 6.0
DEFAULT_FONT_SIZE = 12.0


@dataclass(frozen=True)
class Replacement:
    page_index: int
    item_id: str
    bbox: list[float]
    old_text: str
    new_text: str
    font_size: float | None = None
    font: str | None = None
    color: str | None = None
    origin: list[float] | None = None


def extract_pdf_text(pdf_bytes: bytes, include_ocr: bool = True) -> dict[str, Any]:
    doc = _open_pdf(pdf_bytes)
    pages: list[dict[str, Any]] = []

    for page_index, page in enumerate(doc):
        page_items: list[dict[str, Any]] = []
        text_dict = page.get_text("dict")

        for block_index, block in enumerate(text_dict.get("blocks", [])):
            for line_index, line in enumerate(block.get("lines", [])):
                for span_index, span in enumerate(line.get("spans", [])):
                    text = span.get("text", "").strip()
                    if not text:
                        continue

                    bbox = [round(float(value), 3) for value in span["bbox"]]
                    page_items.append(
                        {
                            "id": f"p{page_index}-b{block_index}-l{line_index}-s{span_index}",
                            "page_index": page_index,
                            "page_number": page_index + 1,
                            "text": text,
                            "bbox": bbox,
                            "origin": _span_origin(span),
                            "font_size": round(float(span.get("size", DEFAULT_FONT_SIZE)), 3),
                            "font": span.get("font", ""),
                            "color": _int_to_rgb(span.get("color", 0)),
                            "source": "pdf",
                        }
                    )

        pages.append(
            {
                "page_index": page_index,
                "page_number": page_index + 1,
                "width": round(float(page.rect.width), 3),
                "height": round(float(page.rect.height), 3),
                "items": page_items,
            }
        )

    ocr_message = ""
    ocr_available = False
    if include_ocr:
        ocr_result = extract_ocr_text(doc, pages)
        pages = ocr_result.pages
        ocr_available = ocr_result.available
        ocr_message = ocr_result.message

    any_items = any(page["items"] for page in pages)
    message = ""
    if not any_items:
        message = ocr_message or "没有找到可复制文字；这个 PDF 可能是扫描件。"
    elif ocr_message:
        message = ocr_message

    return {
        "page_count": len(doc),
        "pages": pages,
        "message": message,
        "ocr_available": ocr_available,
    }


def export_pdf_with_replacements(pdf_bytes: bytes, replacements: list[Replacement]) -> bytes:
    doc = _open_pdf(pdf_bytes)
    replacements_by_page: dict[int, list[Replacement]] = {}

    for replacement in replacements:
        if not (0 <= replacement.page_index < len(doc)):
            raise ValueError(f"Invalid page index: {replacement.page_index}")
        replacements_by_page.setdefault(replacement.page_index, []).append(replacement)

    for page_index, page_replacements in replacements_by_page.items():
        page = doc[page_index]

        for replacement in page_replacements:
            rect = _replacement_rect(replacement.bbox)
            page.add_redact_annot(rect, fill=(1, 1, 1))

        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

        for replacement in page_replacements:
            new_text = replacement.new_text.strip()
            if not new_text:
                continue

            rect = _replacement_rect(replacement.bbox)
            fontname = _font_for_replacement(new_text, replacement.font)
            font_size = replacement.font_size or _fit_font_size(
                new_text, rect, _starting_font_size(rect), fontname
            )
            _insert_replacement_text(
                page,
                rect,
                new_text,
                font_size,
                fontname,
                replacement.color,
                replacement.origin,
            )

    return doc.tobytes(garbage=4, deflate=True)


def save_pdf_with_replacements(
    pdf_bytes: bytes,
    replacements: list[Replacement],
    original_filename: str,
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_bytes = export_pdf_with_replacements(pdf_bytes, replacements)
    output_path = _unique_output_path(output_dir, original_filename)
    output_path.write_bytes(output_bytes)
    return output_path


def _open_pdf(pdf_bytes: bytes) -> fitz.Document:
    try:
        return fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise ValueError("文件不是有效的 PDF。") from exc


def _replacement_rect(bbox: list[float]) -> fitz.Rect:
    if len(bbox) != 4:
        raise ValueError("Replacement bbox must contain four numbers.")
    x0, y0, x1, y1 = [float(value) for value in bbox]
    rect = fitz.Rect(x0 - 1, y0 - 1, x1 + 1, y1 + 2)
    if rect.is_empty or rect.is_infinite:
        raise ValueError("Replacement bbox is invalid.")
    return rect


def _starting_font_size(rect: fitz.Rect) -> float:
    return max(MIN_FONT_SIZE, min(DEFAULT_FONT_SIZE, rect.height * 0.72))


def _fit_font_size(text: str, rect: fitz.Rect, starting_size: float, fontname: str) -> float:
    size = starting_size
    while size > MIN_FONT_SIZE:
        if _text_fits(text, rect, size, fontname):
            return round(size, 2)
        size -= 0.5
    return MIN_FONT_SIZE


def _text_fits(text: str, rect: fitz.Rect, font_size: float, fontname: str) -> bool:
    if font_size * 1.25 > rect.height:
        return False

    try:
        text_width = fitz.get_text_length(text, fontname=fontname, fontsize=font_size)
    except Exception:
        text_width = len(text) * font_size * 0.65

    return text_width <= rect.width


def _insert_replacement_text(
    page: fitz.Page,
    rect: fitz.Rect,
    text: str,
    font_size: float,
    fontname: str,
    color: str | None,
    origin: list[float] | None,
) -> None:
    point = _replacement_origin(rect, origin)
    try:
        page.insert_text(
            point,
            text,
            fontsize=font_size,
            fontname=fontname,
            color=_hex_to_rgb(color),
        )
    except Exception:
        page.insert_text(
            point,
            text,
            fontsize=font_size,
            fontname=_font_for_text(text),
            color=_hex_to_rgb(color),
        )


def _replacement_origin(rect: fitz.Rect, origin: list[float] | None) -> fitz.Point:
    if origin and len(origin) == 2:
        return fitz.Point(float(origin[0]), float(origin[1]))
    return fitz.Point(rect.x0 + 1, rect.y1 - 2)


def _font_for_replacement(text: str, original_font: str | None) -> str:
    if _needs_cjk_font(text):
        return "china-s"
    if original_font:
        return original_font
    return _font_for_text(text)


def _font_for_text(text: str) -> str:
    if _needs_cjk_font(text):
        return "china-s"
    return "helv"


def _needs_cjk_font(text: str) -> bool:
    try:
        text.encode("latin-1")
        return False
    except UnicodeEncodeError:
        return True


def _int_to_rgb(value: int) -> str:
    red = (int(value) >> 16) & 255
    green = (int(value) >> 8) & 255
    blue = int(value) & 255
    return f"#{red:02x}{green:02x}{blue:02x}"


def _span_origin(span: dict[str, Any]) -> list[float]:
    origin = span.get("origin")
    if not origin or len(origin) != 2:
        bbox = span.get("bbox", [0, 0, 0, 0])
        return [round(float(bbox[0]), 3), round(float(bbox[3]), 3)]
    return [round(float(origin[0]), 3), round(float(origin[1]), 3)]


def _hex_to_rgb(value: str | None) -> tuple[float, float, float]:
    if not value:
        return (0, 0, 0)

    match = re.fullmatch(r"#?([0-9a-fA-F]{6})", value.strip())
    if not match:
        return (0, 0, 0)

    raw = match.group(1)
    return (
        int(raw[0:2], 16) / 255,
        int(raw[2:4], 16) / 255,
        int(raw[4:6], 16) / 255,
    )


def _unique_output_path(output_dir: Path, original_filename: str) -> Path:
    source = Path(original_filename or "edited.pdf")
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", source.stem).strip(" .") or "edited"
    candidate = output_dir / f"{stem}-edited.pdf"
    index = 2

    while candidate.exists():
        candidate = output_dir / f"{stem}-edited-{index}.pdf"
        index += 1

    return candidate
