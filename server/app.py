from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

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
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="请上传 PDF 文件。")

    pdf_bytes = await file.read()
    document_id = uuid.uuid4().hex
    pdf_path = _document_path(document_id)

    try:
        extracted = extract_pdf_text(pdf_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    pdf_path.write_bytes(pdf_bytes)
    return {"document_id": document_id, "filename": filename, **extracted}


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
