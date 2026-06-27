#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LABEL="com.codex.pdf-text-replacement"
PLIST_TEMPLATE="${ROOT}/launchd/${LABEL}.plist.template"
PLIST_TARGET="${HOME}/Library/LaunchAgents/${LABEL}.plist"
USER_ID="$(id -u)"

cd "${ROOT}"

if [ ! -d "${ROOT}/.venv" ]; then
  python3 -m venv .venv
fi

. "${ROOT}/.venv/bin/activate"
pip install -r requirements.txt

if ! command -v tesseract >/dev/null 2>&1; then
  echo "提示：未检测到 tesseract，普通 PDF 可用，图片文字 OCR 不可用。可运行：brew install tesseract tesseract-lang"
fi

mkdir -p "${HOME}/Library/LaunchAgents"
sed "s#__ROOT__#${ROOT}#g" "${PLIST_TEMPLATE}" > "${PLIST_TARGET}"

launchctl bootout "gui/${USER_ID}/${LABEL}" >/dev/null 2>&1 || true
sleep 0.5
if ! launchctl bootstrap "gui/${USER_ID}" "${PLIST_TARGET}"; then
  launchctl bootout "gui/${USER_ID}" "${PLIST_TARGET}" >/dev/null 2>&1 || true
  sleep 0.5
  launchctl bootstrap "gui/${USER_ID}" "${PLIST_TARGET}"
fi
launchctl kickstart -k "gui/${USER_ID}/${LABEL}"

echo "正在启动 PDF 信息替换工具..."
for _ in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8000/ >/dev/null 2>&1; then
    echo "PDF 信息替换工具已启动: http://127.0.0.1:8000"
    exit 0
  fi
  sleep 0.5
done

echo "服务启动失败，请查看 /tmp/pdf_text_replacement_uvicorn.err.log" >&2
tail -40 /tmp/pdf_text_replacement_uvicorn.err.log >&2 || true
exit 1
