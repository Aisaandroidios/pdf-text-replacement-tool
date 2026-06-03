# PDF Text Replacement Tool

[中文说明](README.zh-CN.md)

This project is a local web app for reading text from digital PDFs and OCR text from images or scanned documents. It supports PDF, PNG, JPG, WEBP, and TIFF uploads, lets you select text, replace it with new content, and export the edited result. Files stay on your own machine and are not uploaded to any external service.

## Requirements

- macOS
- Python 3.10 or later
- Git
- Tesseract OCR, required for image/scanned-document text recognition

## Start

Install the OCR engine if you need image text recognition:

```bash
brew install tesseract tesseract-lang
```

`tesseract-lang` installs multilingual OCR language packs.

Recommended local background service:

```bash
./scripts/start-server.sh
```

Open:

```text
http://127.0.0.1:8000
```

Stop:

```bash
./scripts/stop-server.sh
```

You can also run it manually in the foreground:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn server.app:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## Usage

1. Click `选择 PDF / 图片` (Choose PDF / Image) to upload a PDF or image.
2. Click `读取文字` (Read Text).
3. Search or select the text you want to replace from the left panel.
4. Enter the new content in the middle panel and click `加入替换` (Add Replacement).
5. If the same text appears multiple times, click `替换所有相同文字` (Replace All Matching Text) to add every exact match.
6. Choose an output type in `导出格式` (Export Format). Image uploads default to their original image format, but you can also export them as PDF.
7. Click `导出图片` (Export Image) or `导出 PDF` (Export PDF).
8. The exported file is saved directly to the macOS Downloads folder, and the full saved path is shown in the page.

## Supported Scope

- Supports ordinary digital PDFs.
- Supports PNG, JPG, WEBP, and TIFF image uploads. Images are converted to single-page PDFs for preview and OCR, while the original image is kept for image-format export.
- Image uploads default to exporting back to the original image format. You can also choose PDF export from the page.
- Supports OCR for images and scanned PDFs when Tesseract is installed.
- Supports multilingual OCR. The app automatically enables all text language packs currently installed in Tesseract. Install the language packs you need, then run `tesseract --list-langs` to see which languages are available on your machine.
- PDF text replacement covers the original text area and writes the new text back into the same region.
- Replacement text inherits the original font size, color, and usable font name when that information is available.
- OCR text in images is replaced by estimating the original image background color, text color, and font size, then writing the new text back into the image to preserve the visual appearance as closely as possible.
- To preserve styling, the app does not automatically shrink overly long replacement text, so very long new text may overflow the original text area.

## Tech Stack

- Python + FastAPI: local backend API for upload, extraction, replacement, and export.
- PyMuPDF / fitz: PDF text extraction, text coordinates, PDF generation, and PDF modification.
- Pillow: image upload handling, image text covering, and image text drawing.
- Tesseract OCR + pytesseract: OCR for images and scanned documents.
- HTML / CSS / JavaScript: frontend UI, file upload, text selection, replacement queue, and export format selection.
- pytest: automated tests for PDF, image, OCR, and export flows.
- launchd + shell scripts: macOS background service start/stop.
- Git + GitHub: version control and open-source publishing.

## Verification

```bash
. .venv/bin/activate
python -m pytest -q
```

## License

MIT License.
