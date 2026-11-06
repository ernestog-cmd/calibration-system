// Builds DOM nodes with textContent only, so data from the API is never interpreted as HTML
export function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);

  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2), value);
    } else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, value);
  }

  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }

  return node;
}

const LABELS = {
  valid: "Valid",
  due_soon: "Due soon",
  expired: "Expired",
  not_required: "Not required",
  active: "Active",
  out_of_service: "Out of service",
  retired: "Retired",
  pass: "Pass",
  fail: "Fail",
  out_of_tolerance: "Out of tolerance",
};

export function badge(value) {
  return h("span", { class: `badge badge-${value}` }, LABELS[value] || value);
}

export function formatDateTime(iso) {
  return iso ? new Date(iso).toLocaleString() : "";
}

export function localDateString(date = new Date()) {
  const pad = (number) => String(number).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function dataTable(headers, rows) {
  return h(
    "div",
    { class: "table-wrap" },
    h(
      "table",
      {},
      h("thead", {}, h("tr", {}, headers.map((text) => h("th", {}, text)))),
      h(
        "tbody",
        {},
        rows.map((cells) => h("tr", {}, cells.map((cell) => h("td", {}, cell)))),
      ),
    ),
  );
}

export function openModal(title, content) {
  const dialog = h("dialog", { class: "modal" }, h("h2", {}, title), content);
  dialog.addEventListener("close", () => dialog.remove());
  document.body.append(dialog);
  dialog.showModal();
  return { close: () => dialog.close() };
}

export function notify(text, isError = false) {
  const toast = h("div", { class: isError ? "toast error" : "toast", role: "status" }, text);
  document.body.append(toast);
  setTimeout(() => toast.remove(), 4500);
}