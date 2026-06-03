# PDF 信息替换工具

本项目是一个本地网页系统，用来读取普通电子 PDF 里的可复制文字，也能通过 OCR 识别图片/扫描件里的文字。它支持上传 PDF、PNG、JPG、WEBP、TIFF，选择某条信息后替换成新信息，并导出修改后的 PDF。它只在本机运行，不会把文件上传到外部服务。

## 环境要求

- macOS
- Python 3.10 或更新版本
- Git
- 如需识别图片/扫描件里的文字：Tesseract OCR

## 启动

如需图片文字 OCR，先安装 OCR 引擎：

```bash
brew install tesseract tesseract-lang
```

`tesseract-lang` 用于安装多语言 OCR 识别包。

推荐使用本机后台服务方式：

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
4. 在中间输入新信息，点击 `加入替换`。
5. 如果同样文字在 PDF 里出现多次，点击 `替换所有相同文字` 可以一次性加入所有相同项。
6. 在 `导出格式` 里选择输出类型。图片上传默认推荐保持原图格式，也可以改成 PDF。
7. 点击 `导出图片` 或 `导出 PDF`。
8. 导出的文件会直接保存到 macOS 下载目录，并在页面顶部和替换列表旁显示完整保存位置。

## 支持范围

- 支持普通电子 PDF。
- 支持 PNG、JPG、WEBP、TIFF 图片上传，图片会先转换为单页 PDF 用于预览和 OCR，同时保留原图片用于导出。
- 图片上传默认导出为原图片格式；如果需要发给别人看，也可以在页面选择导出为 PDF。
- 支持图片/扫描件 PDF 的 OCR 文字识别，需要安装 Tesseract。
- OCR 会自动启用 Tesseract 当前安装的全部文字语言包；安装 `tesseract-lang` 后通常包含英语、中文、法语、德语、日语、韩语、俄语、印地语、维吾尔语等多种语言。可用 `tesseract --list-langs` 查看本机实际可识别语言。
- 替换方式是在原文字区域做白色覆盖，再写入新文字。
- 替换文字会继承原文字的字号、颜色和可用字体名。
- 图片文字来自 OCR，系统会按原图文字区域估算背景色、文字颜色和字号后写回原图，尽量保持原图视觉效果。
- 为了保持样式不变，新文字过长时不会自动缩小字号，可能会超出原文字区域。

## 技术栈

- Python + FastAPI：本地后端接口，处理上传、读取、替换和导出。
- PyMuPDF / fitz：读取 PDF 文字、定位文字坐标、生成和修改 PDF。
- Pillow：处理图片上传，在图片上覆盖旧文字并写入新文字。
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

本项目使用 MIT License。
