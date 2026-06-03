from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import shutil
from typing import Any

import fitz


OCR_DPI = 220
MIN_CONFIDENCE = 35
OCR_LANGUAGE_CODES = (
    "eng",
    "chi_sim",
    "chi_tra",
    "fra",
    "deu",
    "jpn",
    "kor",
    "rus",
    "hin",
    "uig",
)


@dataclass(frozen=True)
class OCRResult:
    pages: list[dict[str, Any]]
    available: bool
    message: str = ""


def extract_ocr_text(doc: fitz.Document, pages: list[dict[str, Any]]) -> OCRResult:
    if not tesseract_available():
        return OCRResult(
            pages=pages,
            available=False,
            message="图片文字 OCR 未启用：请安装 Tesseract 和 Python OCR 依赖。",
        )

    try:
        from PIL import Image
        import pytesseract
    except Exception:
        return OCRResult(
            pages=pages,
            available=False,
            message="图片文字 OCR 未启用：请安装 Pillow 和 pytesseract。",
        )

    tesseract_cmd = tesseract_command()
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    scale = OCR_DPI / 72
    matrix = fitz.Matrix(scale, scale)

    for page_index, page in enumerate(doc):
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        image = Image.open(BytesIO(pixmap.tobytes("png")))
        data = pytesseract.image_to_data(
            image,
            output_type=pytesseract.Output.DICT,
            lang=_ocr_language(pytesseract),
            config="--psm 6",
        )
        ocr_items = ocr_data_to_items(data, page_index, page.rect, scale)
        selectable_items = pages[page_index]["items"]
        pages[page_index]["items"].extend(
            item for item in ocr_items if not overlaps_existing_text(item, selectable_items)
        )

    return OCRResult(pages=pages, available=True)


def tesseract_available() -> bool:
    tesseract_cmd = tesseract_command()
    if tesseract_cmd is None:
        return False
    try:
        import PIL  # noqa: F401
        import pytesseract
    except Exception:
        return False
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    return True


def tesseract_command() -> str | None:
    discovered = shutil.which("tesseract")
    if discovered:
        return discovered

    for candidate in ("/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract"):
        if Path(candidate).exists():
            return candidate
    return None


def _ocr_language(pytesseract: Any) -> str:
    try:
        languages = set(pytesseract.get_languages(config=""))
    except Exception:
        return "eng"

    selected = [language for language in OCR_LANGUAGE_CODES if language in languages]
    return "+".join(selected) if selected else "eng"


def ocr_data_to_items(
    data: dict[str, list[Any]],
    page_index: int,
    page_rect: fitz.Rect,
    scale: float,
) -> list[dict[str, Any]]:
    lines: dict[tuple[int, int, int], list[dict[str, Any]]] = defaultdict(list)

    for index, text in enumerate(data.get("text", [])):
        clean_text = str(text).strip()
        if not clean_text:
            continue
        if _confidence_at(data, index) < MIN_CONFIDENCE:
            continue

        left = float(data["left"][index]) / scale
        top = float(data["top"][index]) / scale
        right = left + float(data["width"][index]) / scale
        bottom = top + float(data["height"][index]) / scale
        bbox = _clamp_bbox([left, top, right, bottom], page_rect)
        if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
            continue

        key = (
            int(data.get("block_num", [0])[index]),
            int(data.get("par_num", [0])[index]),
            int(data.get("line_num", [0])[index]),
        )
        lines[key].append({"text": clean_text, "bbox": bbox, "word": int(data.get("word_num", [0])[index])})

    items: list[dict[str, Any]] = []
    for (block_num, par_num, line_num), words in sorted(lines.items()):
        sorted_words = sorted(words, key=lambda word: word["word"])
        text = " ".join(word["text"] for word in sorted_words)
        bbox = _union_bboxes([word["bbox"] for word in sorted_words])
        height = bbox[3] - bbox[1]
        font_size = round(max(6.0, height * 0.72), 2)
        items.append(
            {
                "id": f"p{page_index}-ocr-b{block_num}-p{par_num}-l{line_num}",
                "page_index": page_index,
                "page_number": page_index + 1,
                "text": text,
                "bbox": [round(value, 3) for value in bbox],
                "origin": [round(bbox[0], 3), round(bbox[3], 3)],
                "font_size": font_size,
                "font": "helv",
                "color": "#000000",
                "source": "ocr",
            }
        )
    return items


def overlaps_existing_text(ocr_item: dict[str, Any], selectable_items: list[dict[str, Any]]) -> bool:
    ocr_bbox = ocr_item["bbox"]
    for item in selectable_items:
        if _intersection_ratio(ocr_bbox, item["bbox"]) >= 0.35:
            return True
    return False


def _confidence_at(data: dict[str, list[Any]], index: int) -> float:
    try:
        return float(data.get("conf", ["-1"])[index])
    except (TypeError, ValueError):
        return -1


def _clamp_bbox(bbox: list[float], page_rect: fitz.Rect) -> list[float]:
    return [
        max(0.0, min(float(page_rect.width), bbox[0])),
        max(0.0, min(float(page_rect.height), bbox[1])),
        max(0.0, min(float(page_rect.width), bbox[2])),
        max(0.0, min(float(page_rect.height), bbox[3])),
    ]


def _union_bboxes(bboxes: list[list[float]]) -> list[float]:
    return [
        min(bbox[0] for bbox in bboxes),
        min(bbox[1] for bbox in bboxes),
        max(bbox[2] for bbox in bboxes),
        max(bbox[3] for bbox in bboxes),
    ]


def _intersection_ratio(first: list[float], second: list[float]) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    if right <= left or bottom <= top:
        return 0.0

    intersection = (right - left) * (bottom - top)
    first_area = max(1.0, (first[2] - first[0]) * (first[3] - first[1]))
    return intersection / first_area
