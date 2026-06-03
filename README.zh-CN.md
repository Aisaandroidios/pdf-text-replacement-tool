# PDF 信息替换工具

[English README](README.md)

这是一个本地网页系统，用来读取普通电子 PDF 里的可复制文字，也能通过 OCR 识别图片或扫描件里的文字。系统支持上传 PDF、PNG、JPG、WEBP、TIFF，选择某条文字后替换成新内容，并导出修改后的结果。所有文件都只在本机处理，不会上传到外部服务。

## 环境要求

- macOS
- Python 3.10 或更新版本
- Git
- Tesseract OCR，用于识别图片或扫描件里的文字

## 启动

如果需要识别图片文字，先安装 OCR 引擎：

```bash
brew install tesseract tesseract-lang
```

`tesseract-lang` 用于安装多语言 OCR 识别包。

推荐使用本机后台服务方式启动：

```bash
./scripts/start-server.sh
```

打开：

```text
http://127.0.0.1:8000
```

关闭：

```bash
./scripts/stop-server.sh
```

也可以手动前台启动：

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn server.app:app --reload --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

## 使用

1. 点击 `选择 PDF / 图片` 上传 PDF 或图片。
2. 点击 `读取文字`。
3. 在左侧搜索或选择要替换的文字。
4. 在中间输入新内容，点击 `加入替换`。
5. 如果同样文字在文件里出现多次，点击 `替换所有相同文字` 可以一次性加入所有完全相同的文字项。
6. 在 `导出格式` 里选择输出类型。图片上传默认推荐保持原图格式，也可以改成 PDF。
7. 点击 `导出图片` 或 `导出 PDF`。
8. 导出的文件会直接保存到 macOS 下载目录，页面上会显示完整保存路径。

## 支持范围

- 支持普通电子 PDF。
- 支持 PNG、JPG、WEBP、TIFF 图片上传。图片会转换为单页 PDF 用于预览和 OCR，同时保留原图用于图片格式导出。
- 图片上传默认导出为原图片格式，也可以在页面里选择导出为 PDF。
- 安装 Tesseract 后，支持图片和扫描版 PDF 的 OCR 文字识别。
- 支持多语言 OCR。系统会自动启用 Tesseract 当前安装的全部文字语言包；需要识别某种语言时，先安装对应的 Tesseract 语言包，再用 `tesseract --list-langs` 查看本机实际可识别语言。
- PDF 文字替换会覆盖原文字区域，并把新文字写回同一区域。
- 如果 PDF 提供字体信息，替换文字会继承原文字的字号、颜色和可用字体名。
- 图片里的 OCR 文字会根据原图文字区域估算背景色、文字颜色和字号，再把新文字写回图片，尽量保持原图视觉效果。
- 为了保持样式，新文字过长时系统不会自动缩小字号，因此过长内容可能超出原文字区域。

## 技术栈

- Python + FastAPI：本地后端接口，处理上传、读取、替换和导出。
- PyMuPDF / fitz：读取 PDF 文字、定位文字坐标、生成和修改 PDF。
- Pillow：处理图片上传、覆盖图片旧文字、写入图片新文字。
- Tesseract OCR + pytesseract：识别图片和扫描件里的文字。
- HTML / CSS / JavaScript：前端页面、文件上传、文字选择、替换列表和导出格式选择。
- pytest：自动测试 PDF、图片、OCR 和导出流程。
- launchd + shell scripts：macOS 后台启动和关闭服务。
- Git + GitHub：版本管理和开源发布。

## 验证

```bash
. .venv/bin/activate
python -m pytest -q
```

## 开源协议

MIT License。
