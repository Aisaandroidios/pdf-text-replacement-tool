const state = {
  documentId: "",
  filename: "",
  pages: [],
  selectedItem: null,
  replacements: new Map(),
};

const uploadForm = document.querySelector("#uploadForm");
const fileInput = document.querySelector("#pdfFile");
const statusText = document.querySelector("#statusText");
const searchInput = document.querySelector("#searchInput");
const textList = document.querySelector("#textList");
const selectedText = document.querySelector("#selectedText");
const sameTextCount = document.querySelector("#sameTextCount");
const newText = document.querySelector("#newText");
const saveReplacement = document.querySelector("#saveReplacement");
const replaceAllSame = document.querySelector("#replaceAllSame");
const replacementList = document.querySelector("#replacementList");
const exportPdf = document.querySelector("#exportPdf");
const pdfPreview = document.querySelector("#pdfPreview");
const lastSavedPath = document.querySelector("#lastSavedPath");

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const file = fileInput.files[0];
  if (!file) {
    setStatus("请选择一个 PDF 文件", "warn");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  setBusy(true, "正在读取 PDF 文字");

  try {
    const response = await fetch("/api/extract", {
      method: "POST",
      body: formData,
    });
    const payload = await readJsonResponse(response);

    state.documentId = payload.document_id;
    state.filename = payload.filename || file.name;
    state.pages = payload.pages || [];
    state.selectedItem = null;
    state.replacements.clear();
    hideSavedPath();
    searchInput.value = "";
    newText.value = "";
    pdfPreview.src = `/api/document/${state.documentId}`;

    renderTextList();
    renderSelection();
    renderReplacements();

    const count = state.pages.reduce((sum, page) => sum + page.items.length, 0);
    setStatus(payload.message || `已读取 ${payload.page_count} 页，${count} 条文字`);
  } catch (error) {
    setStatus(error.message, "warn");
  } finally {
    setBusy(false);
  }
});

searchInput.addEventListener("input", renderTextList);

saveReplacement.addEventListener("click", () => {
  if (!state.selectedItem) return;

  const value = newText.value.trim();
  if (!value) {
    setStatus("请输入替换后的内容", "warn");
    return;
  }

  addReplacement(state.selectedItem, value);

  renderTextList();
  renderReplacements();
  setStatus(`已加入 1 处替换：${state.selectedItem.text}`);
});

replaceAllSame.addEventListener("click", () => {
  if (!state.selectedItem) return;

  const value = newText.value.trim();
  if (!value) {
    setStatus("请输入替换后的内容", "warn");
    return;
  }

  const matches = getItemsWithText(state.selectedItem.text);
  for (const item of matches) {
    addReplacement(item, value);
  }

  renderTextList();
  renderSelection();
  renderReplacements();
  setStatus(`已加入 ${matches.length} 处相同文字替换：${state.selectedItem.text}`);
});

exportPdf.addEventListener("click", async () => {
  if (!state.documentId || state.replacements.size === 0) return;

  setBusy(true, "正在生成并保存 PDF");

  try {
    const response = await fetch("/api/export-save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        document_id: state.documentId,
        filename: state.filename,
        replacements: [...state.replacements.values()],
      }),
    });

    const payload = await readJsonResponse(response);
    showSavedPath(payload.saved_path);
    setStatus(payload.message || `PDF 已保存：${payload.saved_path}`);
  } catch (error) {
    setStatus(error.message, "warn");
  } finally {
    setBusy(false);
  }
});

function renderTextList() {
  const query = searchInput.value.trim().toLowerCase();
  const pages = state.pages
    .map((page) => ({
      ...page,
      items: page.items.filter((item) => !query || item.text.toLowerCase().includes(query)),
    }))
    .filter((page) => page.items.length > 0);

  if (pages.length === 0) {
    textList.className = "text-list empty-state";
    textList.textContent = state.pages.length ? "没有匹配文字" : "暂无文字";
    return;
  }

  textList.className = "text-list";
  textList.innerHTML = "";

  for (const page of pages) {
    const group = document.createElement("section");
    group.className = "page-group";

    const title = document.createElement("div");
    title.className = "page-title";
    title.textContent = `第 ${page.page_number} 页`;
    group.append(title);

    for (const item of page.items) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `text-item${state.selectedItem?.id === item.id ? " active" : ""}`;
      button.dataset.replaced = state.replacements.has(item.id) ? "true" : "false";
      button.textContent = item.text;
      button.addEventListener("click", () => selectItem(item));
      group.append(button);
    }

    textList.append(group);
  }
}

function selectItem(item) {
  state.selectedItem = item;
  const existing = state.replacements.get(item.id);
  newText.value = existing?.new_text || "";
  renderTextList();
  renderSelection();
}

function renderSelection() {
  if (!state.selectedItem) {
    selectedText.textContent = "未选择";
    sameTextCount.textContent = "选择文字后显示相同项数量";
    saveReplacement.disabled = true;
    replaceAllSame.disabled = true;
    return;
  }

  selectedText.textContent = `第 ${state.selectedItem.page_number} 页：${state.selectedItem.text}`;
  const count = getItemsWithText(state.selectedItem.text).length;
  sameTextCount.textContent = `PDF 中共有 ${count} 处完全相同文字`;
  saveReplacement.disabled = false;
  replaceAllSame.disabled = false;
}

function renderReplacements() {
  exportPdf.disabled = state.replacements.size === 0;

  if (state.replacements.size === 0) {
    replacementList.className = "replacement-list empty-state";
    replacementList.textContent = "暂无替换";
    return;
  }

  replacementList.className = "replacement-list";
  replacementList.innerHTML = "";

  for (const replacement of state.replacements.values()) {
    const entry = document.createElement("article");
    entry.className = "replacement-entry";

    const title = document.createElement("strong");
    title.textContent = `第 ${replacement.page_index + 1} 页`;

    const copy = document.createElement("p");
    copy.textContent = `${replacement.old_text} → ${replacement.new_text}`;

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "remove-replacement";
    remove.textContent = "移除";
    remove.addEventListener("click", () => {
      state.replacements.delete(replacement.item_id);
      renderTextList();
      renderReplacements();
      setStatus("已移除替换");
    });

    entry.append(title, copy, remove);
    replacementList.append(entry);
  }
}

function addReplacement(item, value) {
  state.replacements.set(item.id, {
    page_index: item.page_index,
    item_id: item.id,
    bbox: item.bbox,
    old_text: item.text,
    new_text: value,
    font_size: item.font_size,
    font: item.font,
    color: item.color,
    origin: item.origin,
  });
  hideSavedPath();
}

function getItemsWithText(text) {
  return state.pages.flatMap((page) => page.items).filter((item) => item.text === text);
}

async function readJsonResponse(response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || "请求失败");
  }
  return payload;
}

function setBusy(isBusy, message = "") {
  uploadForm.querySelector("button").disabled = isBusy;
  saveReplacement.disabled = isBusy || !state.selectedItem;
  replaceAllSame.disabled = isBusy || !state.selectedItem;
  exportPdf.disabled = isBusy || state.replacements.size === 0;
  if (message) setStatus(message);
}

function setStatus(message, tone = "") {
  statusText.textContent = message;
  statusText.classList.toggle("tone-warn", tone === "warn");
}

function showSavedPath(path) {
  lastSavedPath.hidden = false;
  lastSavedPath.textContent = `保存位置：${path}`;
}

function hideSavedPath() {
  lastSavedPath.hidden = true;
  lastSavedPath.textContent = "";
}
