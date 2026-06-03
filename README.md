# PDF 信息替换工具

本项目是一个本地网页系统，用来读取普通电子 PDF 里的可复制文字，也能通过 OCR 识别图片/扫描件里的文字，选择某条信息后替换成新信息，并导出修改后的 PDF。它只在本机运行，不会把 PDF 上传到外部服务。

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

1. 点击 `选择 PDF` 上传文件。
2. 点击 `读取文字`。
3. 在左侧搜索或选择要替换的文字。
4. 在中间输入新信息，点击 `加入替换`。
5. 如果同样文字在 PDF 里出现多次，点击 `替换所有相同文字` 可以一次性加入所有相同项。
6. 点击 `导出 PDF`。
7. 导出的文件会直接保存到 macOS 下载目录，并在页面顶部和替换列表旁显示完整保存位置。

## 支持范围

- 支持普通电子 PDF。
- 支持图片/扫描件 PDF 的 OCR 文字识别，需要安装 Tesseract。
- 替换方式是在原文字区域做白色覆盖，再写入新文字。
- 替换文字会继承原文字的字号、颜色和可用字体名。
- 图片文字来自 OCR，系统能识别位置并替换，但图片里的原始字体和复杂背景无法 100% 还原。
- 为了保持样式不变，新文字过长时不会自动缩小字号，可能会超出原文字区域。

## 验证

```bash
. .venv/bin/activate
python -m pytest -q
```

## 开源协议

本项目使用 MIT License。
