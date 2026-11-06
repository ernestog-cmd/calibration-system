import { api } from "../api.js";
import { badge, dataTable, formatDateTime, h } from "../ui.js";

const PAGE_SIZE = 25;

const STATUS_OPTIONS = [
  ["", "Any status"],
  ["active", "Active"],
  ["out_of_service", "Out of service"],
  ["retired", "Retired"],
];

const STATE_OPTIONS = [
  ["", "Any calibration state"],
  ["valid", "Valid"],
  ["due_soon", "Due soon"],
  ["expired", "Expired"],
  ["not_required", "Not required"],
];

const emptyFilters = () => ({
  q: "",
  equipment_type: "",
  location: "",
  status: "",
  calibration_state: "",
  page: 0,
});

// Kept at module level so the filters survive going to a detail page and back
let filters = emptyFilters();

export function renderEquipment(container, user, args) {
  const [id] = args;
  return id ? renderDetail(container, id) : renderList(container);
}

function textFilter(label, name) {
  return h(
    "label",
    {},
    label,
    h("input", { name, value: filters[name], autocomplete: "off" }),
  );
}

function selectFilter(label, name, options) {
  return h(
    "label",
    {},
    label,
    h(
      "select",
      { name },
      options.map(([value, text]) => h("option", { value, selected: filters[name] === value }, text)),
    ),
  );
}

async function renderList(container) {
  const results = h("div");
  let requestId = 0;

  async function load() {
    const current = ++requestId;
    results.replaceChildren(h("p", { class: "muted" }, "Loading..."));

    try {
      // One extra row tells us whether there is a next page
      const items = await api("/equipment", {
        params: {
          q: filters.q.trim(),
          equipment_type: filters.equipment_type.trim(),
          location: filters.location.trim(),
          status: filters.status,
          calibration_state: filters.calibration_state,
          skip: filters.page * PAGE_SIZE,
          limit: PAGE_SIZE + 1,
        },
      });
      if (current !== requestId) return;

      const hasNext = items.length > PAGE_SIZE;
      const rows = items.slice(0, PAGE_SIZE);

      if (rows.length === 0) {
        results.replaceChildren(h("p", { class: "muted" }, "No equipment matches these filters."));
        return;
      }

      results.replaceChildren(
        dataTable(
          ["Code", "Name", "Type", "Location", "Responsible", "Status", "Calibration", "Due"],
          rows.map((item) => [
            h("a", { href: `#/equipment/${item.id}` }, item.asset_code),
            item.name,
            item.equipment_type,
            item.location,
            item.responsible_username,
            badge(item.status),
            badge(item.calibration_state),
            item.calibration_due_date || "—",
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
      if (current !== requestId) return;
      if (error.status === 401) return;
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
          q: data.get("q"),
          equipment_type: data.get("equipment_type"),
          location: data.get("location"),
          status: data.get("status"),
          calibration_state: data.get("calibration_state"),
          page: 0,
        };
        load();
      },
    },
    textFilter("Search", "q"),
    textFilter("Type", "equipment_type"),
    textFilter("Location", "location"),
    selectFilter("Status", "status", STATUS_OPTIONS),
    selectFilter("Calibration", "calibration_state", STATE_OPTIONS),
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
            renderList(container);
          },
        },
        "Clear",
      ),
    ),
  );

  container.replaceChildren(h("h1", {}, "Equipment"), h("div", { class: "card" }, form, results));
  await load();
}

function field(label, value) {
  return h("div", {}, h("dt", {}, label), h("dd", {}, value));
}

async function renderDetail(container, id) {
  const equipment = await api(`/equipment/${encodeURIComponent(id)}`);
  const [calibrations, usage] = await Promise.all([
    api(`/equipment/${equipment.id}/calibrations`, { params: { limit: 50 } }),
    api("/usage", { params: { asset_code: equipment.asset_code, limit: 10 } }),
  ]);

  const calibrationSection = !equipment.requires_calibration
    ? h("p", { class: "muted" }, "This equipment does not require calibration.")
    : calibrations.length === 0
      ? h("p", { class: "muted" }, "No calibrations recorded yet.")
      : dataTable(
          ["Calibration date", "Due date", "Result", "Performed by", "Certificate"],
          calibrations.map((item) => [
            item.calibration_date,
            item.due_date,
            badge(item.result),
            item.performed_by,
            item.certificate_filename || "—",
          ]),
        );

  const usageSection =
    usage.length === 0
      ? h("p", { class: "muted" }, "This equipment has not been used in any lot yet.")
      : dataTable(
          ["Used at", "Lot", "Part number", "Operation", "State at use", "Recorded by"],
          usage.map((item) => [
            formatDateTime(item.used_at),
            item.lot_id,
            item.part_number || "—",
            item.operation || "—",
            badge(item.calibration_state_at_use),
            item.recorded_by,
          ]),
        );

  container.replaceChildren(
    h("a", { href: "#/equipment", class: "back" }, "← Back to equipment"),
    h("h1", {}, `${equipment.asset_code} · ${equipment.name}`),
    h(
      "div",
      { class: "stack" },
      h(
        "div",
        { class: "card" },
        h(
          "dl",
          { class: "details" },
          field("Type", equipment.equipment_type),
          field("Serial number", equipment.serial_number),
          field("Location", equipment.location),
          field("Responsible", equipment.responsible_username),
          field("Status", badge(equipment.status)),
          field("Requires calibration", equipment.requires_calibration ? "Yes" : "No"),
          field(
            "Calibration interval",
            equipment.calibration_interval_days ? `${equipment.calibration_interval_days} days` : "—",
          ),
          field("Calibration state", badge(equipment.calibration_state)),
          field("Calibration due", equipment.calibration_due_date || "—"),
        ),
      ),
      h("div", { class: "card" }, h("h2", {}, "Calibration history"), calibrationSection),
      h(
        "div",
        { class: "card" },
        h("h2", {}, "Recent lot usage"),
        usageSection,
        usage.length === 10 ? h("p", { class: "muted" }, "Showing the 10 most recent uses.") : null,
      ),
    ),
  );
}