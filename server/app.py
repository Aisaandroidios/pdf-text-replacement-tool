from __future__ import annotations

from io import BytesIO
import json
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import fitz
from PIL import Image, UnidentifiedImageError

from server.image_service import (
    export_image_with_replacements,
    image_format_for_extension,
    image_media_type,
    save_image_with_replacements,
)
from server.pdf_service import (
    Replacement,
    export_pdf_with_replacements,
    extract_pdf_text,
    save_pdf_with_replacements,
)


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
STORAGE_DIR = Path(tempfile.gettempdir()) / "pdf-text-replacement-system"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOADS_DIR = Path.home() / "Downloads"
SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
MAX_IMAGE_PDF_WIDTH = 612

app = FastAPI(title="PDF Text Replacement System")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ReplacementPayload(BaseModel):
    page_index: int
    item_id: str
    bbox: list[float] = Field(min_length=4, max_length=4)
    old_text: str
    new_text: str
    font_size: float | None = None
    font: str | None = None
    color: str | None = None
    origin: list[float] | None = Field(default=None, min_length=2, max_length=2)


class ExportPayload(BaseModel):
    document_id: str
    filename: str | None = None
    output_format: str | None = None
    replacements: list[ReplacementPayload]


@app.get("/", response_model=None)
def index():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse("<h1>PDF Text Replacement System</h1>")


@app.post("/api/extract")
async def extract(file: UploadFile = File(...)) -> dict:
    filename = file.filename or "uploaded.pdf"

    uploaded_bytes = await file.read()
    try:
        prepared = _uploaded_file_to_pdf(filename, uploaded_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    document_id = uuid.uuid4().hex
    pdf_path = _document_path(document_id)

    try:
        extracted = extract_pdf_text(prepared["pdf_bytes"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    pdf_path.write_bytes(prepared["pdf_bytes"])
    _source_path(document_id, prepared["source_extension"]).write_bytes(prepared["source_bytes"])
    _metadata_path(document_id).write_text(
        json.dumps(_document_metadata(prepared), ensure_ascii=False),
        encoding="utf-8",
    )

    return {
        "document_id": document_id,
        "filename": prepared["original_filename"],
        "preview_filename": prepared["preview_filename"],
        "source_type": prepared["source_type"],
        "source_format": prepared["source_format"],
        "recommended_export_format": _recommended_export_format(prepared["source_type"]),
        "export_options": _export_options(prepared["source_type"], prepared["source_format"]),
        **extracted,
    }


@app.get("/api/document/{document_id}")
def document(document_id: str) -> FileResponse:
    pdf_path = _document_path(document_id)
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="找不到这个 PDF，请重新上传。")
    return FileResponse(pdf_path, media_type="application/pdf", filename="original.pdf")


@app.post("/api/export")
def export(payload: ExportPayload) -> Response:
    pdf_path = _document_path(payload.document_id)
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="找不到这个 PDF，请重新上传。")

    replacements = _replacement_models(payload.replacements)
    metadata = _read_metadata(payload.document_id)
    output_format = _resolved_output_format(payload.output_format, metadata)

    if output_format == "source":
        try:
            output = export_image_with_replacements(
                _source_path(payload.document_id, metadata["source_extension"]).read_bytes(),
                replacements,
                _pdf_page_size(pdf_path),
                metadata.get("source_format"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        media_type = image_media_type(metadata.get("source_format"))
        filename = _download_filename(payload.filename or metadata["original_filename"], metadata["source_format"])
        return Response(
            content=output,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    try:
        output = export_pdf_with_replacements(pdf_path.read_bytes(), replacements)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return Response(
        content=output,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="edited.pdf"'},
    )


@app.post("/api/export-save")
def export_save(payload: ExportPayload) -> dict[str, str]:
    pdf_path = _document_path(payload.document_id)
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="找不到这个 PDF，请重新上传。")

    metadata = _read_metadata(payload.document_id)
    output_format = _resolved_output_format(payload.output_format, metadata)
    replacements = _replacement_models(payload.replacements)

    try:
        if output_format == "source":
            output_path = save_image_with_replacements(
                _source_path(payload.document_id, metadata["source_extension"]).read_bytes(),
                replacements,
                payload.filename or metadata["original_filename"],
                DOWNLOADS_DIR,
                _pdf_page_size(pdf_path),
                metadata.get("source_format"),
            )
            media_type = image_media_type(metadata.get("source_format"))
        else:
            output_path = save_pdf_with_replacements(
                pdf_path.read_bytes(),
                replacements,
                payload.filename or "edited.pdf",
                DOWNLOADS_DIR,
            )
            media_type = "application/pdf"
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "filename": output_path.name,
        "saved_path": str(output_path),
        "output_format": output_format,
        "media_type": media_type,
        "message": f"文件已保存到 {output_path}",
    }


def _replacement_models(items: list[ReplacementPayload]) -> list[Replacement]:
    return [
        Replacement(
            page_index=item.page_index,
            item_id=item.item_id,
            bbox=item.bbox,
            old_text=item.old_text,
            new_text=item.new_text,
            font_size=item.font_size,
            font=item.font,
            color=item.color,
            origin=item.origin,
        )
        for item in items
    ]


def _document_path(document_id: str) -> Path:
    if not document_id or any(char not in "0123456789abcdef" for char in document_id):
        raise HTTPException(status_code=400, detail="PDF 编号无效。")
    return STORAGE_DIR / f"{document_id}.pdf"


def _uploaded_file_to_pdf(filename: str, uploaded_bytes: bytes) -> dict[str, bytes | str]:
    source = Path(filename)
    extension = source.suffix.lower()

    if extension == ".pdf":
        return {
            "pdf_bytes": uploaded_bytes,
            "source_bytes": uploaded_bytes,
            "original_filename": filename,
            "preview_filename": filename,
            "source_type": "pdf",
            "source_format": "PDF",
            "source_extension": ".pdf",
        }

    if extension not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ValueError("请上传 PDF 或图片文件。支持 PDF、PNG、JPG、WEBP、TIFF。")

    try:
        image = Image.open(BytesIO(uploaded_bytes))
        image.load()
    except UnidentifiedImageError as exc:
        raise ValueError("图片文件无效，无法读取。") from exc

    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    elif image.mode == "L":
        image = image.convert("RGB")

    stream = BytesIO()
    image.save(stream, format="PNG")

    width, height = _image_pdf_size(image.width, image.height)
    doc = fitz.open()
    page = doc.new_page(width=width, height=height)
    page.insert_image(page.rect, stream=stream.getvalue())
    preview_filename = f"{source.stem or 'image'}.pdf"
    return {
        "pdf_bytes": doc.tobytes(garbage=4, deflate=True),
        "source_bytes": uploaded_bytes,
        "original_filename": filename,
        "preview_filename": preview_filename,
        "source_type": "image",
        "source_format": image_format_for_extension(extension),
        "source_extension": extension,
    }


def _image_pdf_size(width: int, height: int) -> tuple[float, float]:
    if width <= 0 or height <= 0:
        raise ValueError("图片尺寸无效。")

    scale = min(1.0, MAX_IMAGE_PDF_WIDTH / width)
    return round(width * scale, 3), round(height * scale, 3)


def _metadata_path(document_id: str) -> Path:
    return STORAGE_DIR / f"{document_id}.json"


def _source_path(document_id: str, extension: str) -> Path:
    safe_extension = extension if extension.startswith(".") else f".{extension}"
    return STORAGE_DIR / f"{document_id}.source{safe_extension.lower()}"


def _document_metadata(prepared: dict[str, bytes | str]) -> dict[str, str]:
    return {
        "original_filename": str(prepared["original_filename"]),
        "preview_filename": str(prepared["preview_filename"]),
        "source_type": str(prepared["source_type"]),
        "source_format": str(prepared["source_format"]),
        "source_extension": str(prepared["source_extension"]),
    }


def _read_metadata(document_id: str) -> dict[str, str]:
    metadata_path = _metadata_path(document_id)
    if not metadata_path.exists():
        return {
            "original_filename": "edited.pdf",
            "preview_filename": "edited.pdf",
            "source_type": "pdf",
            "source_format": "PDF",
            "source_extension": ".pdf",
        }

    return json.loads(metadata_path.read_text(encoding="utf-8"))


def _recommended_export_format(source_type: str) -> str:
    return "source" if source_type == "image" else "pdf"


def _export_options(source_type: str, source_format: str) -> list[dict[str, str]]:
    if source_type == "image":
        return [
            {"value": "source", "label": f"保持原图格式 {source_format}"},
            {"value": "pdf", "label": "导出 PDF"},
        ]
    return [{"value": "pdf", "label": "导出 PDF"}]


def _resolved_output_format(output_format: str | None, metadata: dict[str, str]) -> str:
    if output_format == "pdf":
        return "pdf"
    if output_format in (None, "", "auto", "source") and metadata.get("source_type") == "image":
        return "source"
    return "pdf"


def _pdf_page_size(pdf_path: Path) -> tuple[float, float]:
    doc = fitz.open(pdf_path)
    page = doc[0]
    return float(page.rect.width), float(page.rect.height)


def _download_filename(filename: str, source_format: str | None) -> str:
    source = Path(filename or "edited")
    extension = {
        "JPEG": ".jpg",
        "PNG": ".png",
        "TIFF": ".tiff",
        "WEBP": ".webp",
    }.get(str(source_format or "PNG").upper(), ".png")
    return f"{source.stem or 'edited'}-edited{extension}"
