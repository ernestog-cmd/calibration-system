import { api, downloadFile } from "../api.js";
import { badge, dataTable, h, localDateString, notify } from "../ui.js";

const STATE_OPTIONS = [
  ["", "Any state"],
  ["valid", "Valid"],
  ["due_soon", "Due soon"],
  ["expired", "Expired"],
  ["not_required", "Not required"],
];

const RESULT_OPTIONS = [
  ["", "Any result"],
  ["pass", "Pass"],
  ["fail", "Fail"],
  ["out_of_tolerance", "Out of tolerance"],
];

function textField(label, name, type = "text") {
  return h("label", {}, label, h("input", { name, type, autocomplete: "off" }));
}

function selectField(label, name, options) {
  return h(
    "label",
    {},
    label,
    h("select", { name }, options.map(([value, text]) => h("option", { value }, text))),
  );
}

function exportCard(title, description, path, filePrefix, fields) {
  const button = h("button", { type: "submit", class: "primary" }, "Download CSV");

  const form = h(
    "form",
    {
      class: "toolbar",
      onsubmit: async (event) => {
        event.preventDefault();

        const params = new URLSearchParams();
        for (const [key, value] of new FormData(form).entries()) {
          const text = String(value).trim();
          if (text) params.set(key, text);
        }
        const query = params.toString();

        button.disabled = true;
        try {
          await downloadFile(query ? `${path}?${query}` : path, `${filePrefix}_${localDateString()}.csv`);
        } catch (error) {
          if (error.status !== 401) notify(error.message, true);
        } finally {
          button.disabled = false;
        }
      },
    },
    fields,
    h("div", { class: "actions" }, button),
  );

  return h("div", { class: "card" }, h("h2", {}, title), h("p", { class: "muted" }, description), form);
}

function failedCalibrations() {
  const results = h("div");
  let requestId = 0;

  async function load(params = {}) {
    const current = ++requestId;
    results.replaceChildren(h("p", { class: "muted" }, "Loading..."));

    try {
      const items = await api("/reports/failed-calibrations", { params: { ...params, limit: 50 } });
      if (current !== requestId) return;

      if (items.length === 0) {
        results.replaceChildren(h("p", { class: "muted" }, "No failed calibrations in this period."));
        return;
      }

      results.replaceChildren(
        dataTable(
          ["Calibration date", "Equipment", "Result", "Due date", "Performed by"],
          items.map((item) => [
            item.calibration_date,
            h("a", { href: `#/equipment/${item.equipment_id}` }, `${item.asset_code} · ${item.equipment_name}`),
            badge(item.result),
            item.due_date,
            item.performed_by,
          ]),
        ),
        items.length === 50 ? h("p", { class: "muted" }, "Showing the 50 most recent.") : null,
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
        load({ from_date: data.get("from_date"), to_date: data.get("to_date") });
      },
    },
    textField("From", "from_date", "date"),
    textField("To", "to_date", "date"),
    h(
      "div",
      { class: "actions" },
      h("button", { type: "submit", class: "primary" }, "Filter"),
      h(
        "button",
        {
          type: "button",
          onclick: () => {
            form.reset();
            load();
          },
        },
        "Clear",
      ),
    ),
  );

  load();
  return h(
    "div",
    { class: "card" },
    h("h2", {}, "Failed calibrations"),
    h("p", { class: "muted" }, "Calibrations that failed or were out of tolerance, newest first."),
    form,
    results,
  );
}

export async function renderReports(container) {
  container.replaceChildren(
    h("div", { class: "page-header" }, h("h1", {}, "Reports")),
    h(
      "div",
      { class: "stack" },
      failedCalibrations(),
      exportCard(
        "Equipment export",
        "Every piece of equipment with its calibration state and due date.",
        "/reports/export/equipment",
        "equipment",
        [selectField("Calibration state", "calibration_state", STATE_OPTIONS)],
      ),
      exportCard(
        "Lot usage export",
        "Where each piece of equipment was used. Days are counted in UTC.",
        "/reports/export/usage",
        "usage",
        [
          textField("Equipment code", "asset_code"),
          textField("Lot", "lot_id"),
          textField("Part number", "part_number"),
          textField("From", "from_date", "date"),
          textField("To", "to_date", "date"),
        ],
      ),
      exportCard(
        "Calibrations export",
        "The full calibration history.",
        "/reports/export/calibrations",
        "calibrations",
        [
          selectField("Result", "result", RESULT_OPTIONS),
          textField("From", "from_date", "date"),
          textField("To", "to_date", "date"),
        ],
      ),
    ),
  );
}