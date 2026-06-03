#!/usr/bin/env bash
set -euo pipefail

LABEL="com.codex.pdf-text-replacement"
USER_ID="$(id -u)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

launchctl bootout "gui/${USER_ID}/${LABEL}" >/dev/null 2>&1 || true
rm -f "${HOME}/Library/LaunchAgents/${LABEL}.plist"
rm -f "${ROOT}/.server.pid"

echo "PDF 信息替换工具已停止"
