from __future__ import annotations

from io import BytesIO
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import fitz
from PIL import Image, UnidentifiedImageError

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
        pdf_bytes, stored_filename = _uploaded_file_to_pdf(filename, uploaded_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    document_id = uuid.uuid4().hex
    pdf_path = _document_path(document_id)

    try:
        extracted = extract_pdf_text(pdf_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    pdf_path.write_bytes(pdf_bytes)
    return {"document_id": document_id, "filename": stored_filename, **extracted}


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

    try:
        output_path = save_pdf_with_replacements(
            pdf_path.read_bytes(),
            _replacement_models(payload.replacements),
            payload.filename or "edited.pdf",
            DOWNLOADS_DIR,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "filename": output_path.name,
        "saved_path": str(output_path),
        "message": f"PDF 已保存到 {output_path}",
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


def _uploaded_file_to_pdf(filename: str, uploaded_bytes: bytes) -> tuple[bytes, str]:
    source = Path(filename)
    extension = source.suffix.lower()

    if extension == ".pdf":
        return uploaded_bytes, filename

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
    stored_filename = f"{source.stem or 'image'}.pdf"
    return doc.tobytes(garbage=4, deflate=True), stored_filename


def _image_pdf_size(width: int, height: int) -> tuple[float, float]:
    if width <= 0 or height <= 0:
        raise ValueError("图片尺寸无效。")

    scale = min(1.0, MAX_IMAGE_PDF_WIDTH / width)
    return round(width * scale, 3), round(height * scale, 3)
