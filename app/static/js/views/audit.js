import { api } from "../api.js";
import { badge, dataTable, formatDateTime, h, openModal } from "../ui.js";

const PAGE_SIZE = 25;

const ENTITY_TYPES = ["user", "equipment", "calibration", "usage", "auth", "system"];
const ACTIONS = [
  "create",
  "update",
  "login",
  "login_failed",
  "upload_certificate",
  "auto_out_of_service",
  "alert_digest_sent",
  "alert_digest_generated",
  "alert_digest_failed",
];

// Fields whose value is one of the known states, shown with the colored badge
const STATE_FIELDS = new Set(["status", "result", "calibration_state_at_use"]);

const emptyFilters = () => ({
  username: "",
  action: "",
  entity_type: "",
  entity_id: "",
  from_date: "",
  to_date: "",
  page: 0,
});

// Kept at module level so the filters survive going to another page and back
let filters = emptyFilters();

const RAW_STYLE =
  "margin:0.5rem 0 0;white-space:pre-wrap;word-break:break-word;font-family:ui-monospace,Menlo,Consolas,monospace;" +
  "font-size:0.8rem;background:#f1f4fb;padding:0.6rem;border-radius:8px;";

function humanize(text) {
  const spaced = String(text).replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function formatValue(field, value) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (STATE_FIELDS.has(field) && typeof value === "string") return badge(value);
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}T/.test(value)) return formatDateTime(value);
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function hasData(value) {
  return value !== null && value !== undefined && Object.keys(value).length > 0;
}

function changesTable(entry) {
  const before = hasData(entry.old_value) ? entry.old_value : null;
  const after = hasData(entry.new_value) ? entry.new_value : null;

  if (!before && !after) return h("p", { class: "muted" }, "No details were recorded for this entry.");

  if (before) {
    const fields = [...new Set([...Object.keys(before), ...Object.keys(after || {})])];
    return dataTable(
      ["Field", "Before", "After"],
      fields.map((field) => [humanize(field), formatValue(field, before[field]), formatValue(field, (after || {})[field])]),
    );
  }

  return dataTable(
    ["Field", "Value"],
    Object.entries(after).map(([field, value]) => [humanize(field), formatValue(field, value)]),
  );
}

function showDetails(entry) {
  const content = h(
    "div",
    {},
    h(
      "p",
      { class: "muted" },
      `${humanize(entry.action)} · ${humanize(entry.entity_type)} ${entry.entity_id} · by ${entry.username} · ${formatDateTime(entry.timestamp)}`,
    ),
    changesTable(entry),
    h(
      "details",
      { style: "margin-top:1rem;" },
      h("summary", { class: "muted" }, "Raw data"),
      h("pre", { style: RAW_STYLE }, JSON.stringify({ old_value: entry.old_value, new_value: entry.new_value }, null, 2)),
    ),
    h("div", { class: "form-actions" }, h("button", { type: "button", onclick: () => modal.close() }, "Close")),
  );
  const modal = openModal(`Audit entry #${entry.id}`, content);
}

function textFilter(label, name, type = "text") {
  return h("label", {}, label, h("input", { name, type, value: filters[name], autocomplete: "off" }));
}

function selectFilter(label, name, values) {
  return h(
    "label",
    {},
    label,
    h(
      "select",
      { name },
      h("option", { value: "" }, "Any"),
      values.map((value) => h("option", { value, selected: filters[name] === value }, humanize(value))),
    ),
  );
}

export async function renderAudit(container) {
  const results = h("div");
  let requestId = 0;

  async function load() {
    const current = ++requestId;
    results.replaceChildren(h("p", { class: "muted" }, "Loading..."));

    try {
      // One extra row tells us whether there is a next page
      const items = await api("/audit", {
        params: {
          username: filters.username.trim(),
          action: filters.action,
          entity_type: filters.entity_type,
          entity_id: filters.entity_id.trim(),
          from_date: filters.from_date,
          to_date: filters.to_date,
          skip: filters.page * PAGE_SIZE,
          limit: PAGE_SIZE + 1,
        },
      });
      if (current !== requestId) return;

      const hasNext = items.length > PAGE_SIZE;
      const rows = items.slice(0, PAGE_SIZE);

      if (rows.length === 0) {
        results.replaceChildren(h("p", { class: "muted" }, "No audit entries match these filters."));
        return;
      }

      results.replaceChildren(
        dataTable(
          ["When", "User", "Action", "Record", "Id", ""],
          rows.map((entry) => [
            formatDateTime(entry.timestamp),
            entry.username,
            humanize(entry.action),
            humanize(entry.entity_type),
            entry.entity_type === "equipment"
              ? h("a", { href: `#/equipment/${entry.entity_id}` }, entry.entity_id)
              : entry.entity_id,
            h("button", { type: "button", class: "small", onclick: () => showDetails(entry) }, "Details"),
          ]),
        ),
        h(
          "div",
          { class: "pager" },
          h(
            "button",
            {
              type: "button",
              disabled: filters.page === 0,
              onclick: () => {
                filters.page -= 1;
                load();
              },
            },
            "Previous",
          ),
          h("span", { class: "muted" }, `Page ${filters.page + 1}`),
          h(
            "button",
            {
              type: "button",
              disabled: !hasNext,
              onclick: () => {
                filters.page += 1;
                load();
              },
            },
            "Next",
          ),
        ),
      );
    } catch (error) {
      if (current !== requestId || error.status === 401) return;
      results.replaceChildren(h("p", { class: "error" }, error.message));
    }
  }

  const form = h(
    "form",
    {
      class: "toolbar",
      onsubmit: (event) => {
        event.preventDefault();
        const data = new FormData(form);
        filters = {
          username: data.get("username"),
          action: data.get("action"),
          entity_type: data.get("entity_type"),
          entity_id: data.get("entity_id"),
          from_date: data.get("from_date"),
          to_date: data.get("to_date"),
          page: 0,
        };
        load();
      },
    },
    textFilter("User", "username"),
    selectFilter("Action", "action", ACTIONS),
    selectFilter("Record type", "entity_type", ENTITY_TYPES),
    textFilter("Record id", "entity_id"),
    textFilter("From (UTC day)", "from_date", "date"),
    textFilter("To (UTC day)", "to_date", "date"),
    h(
      "div",
      { class: "actions" },
      h("button", { type: "submit", class: "primary" }, "Search"),
      h(
        "button",
        {
          type: "button",
          onclick: () => {
            filters = emptyFilters();
            renderAudit(container);
          },
        },
        "Clear",
      ),
    ),
  );

  container.replaceChildren(
    h("div", { class: "page-header" }, h("h1", {}, "Audit log")),
    h("div", { class: "card" }, form, results),
  );
  await load();
}