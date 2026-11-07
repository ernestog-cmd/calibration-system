import { api } from "../api.js";
import { badge, dataTable, formatDateTime, h, notify, openModal } from "../ui.js";

const PAGE_SIZE = 25;
const WRITERS = ["admin", "technician"];

const emptyFilters = () => ({
  asset_code: "",
  lot_id: "",
  part_number: "",
  from_date: "",
  to_date: "",
  page: 0,
});

// Kept at module level so the filters survive going to another page and back
let filters = emptyFilters();

function filterInput(label, name, type = "text") {
  return h("label", {}, label, h("input", { name, type, value: filters[name], autocomplete: "off" }));
}

function openUsageForm(onSaved) {
  const field = (label, name, { required = false, maxlength = 100 } = {}) =>
    h("label", {}, label, h("input", { name, required, maxlength, autocomplete: "off" }));

  const error = h("p", { class: "error", hidden: true });
  const save = h("button", { type: "submit", class: "primary" }, "Register usage");
  const cancel = h("button", { type: "button", onclick: () => modal.close() }, "Cancel");

  const form = h(
    "form",
    {},
    field("Equipment code", "asset_code", { required: true, maxlength: 50 }),
    field("Lot", "lot_id", { required: true }),
    field("Part number (optional)", "part_number"),
    field("Operation (optional)", "operation"),
    field("Notes (optional)", "notes", { maxlength: 500 }),
    h("p", { class: "muted" }, "Equipment that is expired, out of service or retired cannot be used."),
    error,
    h("div", { class: "form-actions" }, cancel, save),
  );

  const modal = openModal("Register equipment usage", form);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    save.disabled = true;

    const data = new FormData(form);
    const payload = {
      asset_code: data.get("asset_code").trim(),
      lot_id: data.get("lot_id").trim(),
    };
    for (const name of ["part_number", "operation", "notes"]) {
      const value = data.get(name).trim();
      if (value) payload[name] = value;
    }

    try {
      await api("/usage", { method: "POST", json: payload });
      modal.close();
      notify("Usage recorded");
      onSaved();
    } catch (failure) {
      if (failure.status === 401) return;
      error.textContent = failure.message;
      error.hidden = false;
    } finally {
      save.disabled = false;
    }
  });
}

export async function renderUsage(container, user) {
  const results = h("div");
  let requestId = 0;

  async function load() {
    const current = ++requestId;
    results.replaceChildren(h("p", { class: "muted" }, "Loading..."));

    try {
      // One extra row tells us whether there is a next page
      const items = await api("/usage", {
        params: {
          asset_code: filters.asset_code.trim(),
          lot_id: filters.lot_id.trim(),
          part_number: filters.part_number.trim(),
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
        results.replaceChildren(h("p", { class: "muted" }, "No usage records match these filters."));
        return;
      }

      results.replaceChildren(
        dataTable(
          ["Used at", "Equipment", "Lot", "Part number", "Operation", "State at use", "Recorded by"],
          rows.map((item) => [
            formatDateTime(item.used_at),
            h("a", { href: `#/equipment/${item.equipment_id}` }, `${item.asset_code} · ${item.equipment_name}`),
            item.lot_id,
            item.part_number || "—",
            item.operation || "—",
            badge(item.calibration_state_at_use),
            item.recorded_by,
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
          asset_code: data.get("asset_code"),
          lot_id: data.get("lot_id"),
          part_number: data.get("part_number"),
          from_date: data.get("from_date"),
          to_date: data.get("to_date"),
          page: 0,
        };
        load();
      },
    },
    filterInput("Equipment code", "asset_code"),
    filterInput("Lot", "lot_id"),
    filterInput("Part number", "part_number"),
    filterInput("From (UTC day)", "from_date", "date"),
    filterInput("To (UTC day)", "to_date", "date"),
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
            renderUsage(container, user);
          },
        },
        "Clear",
      ),
    ),
  );

  const registerButton = WRITERS.includes(user.role)
    ? h(
        "button",
        {
          type: "button",
          class: "primary",
          onclick: () =>
            openUsageForm(() => {
              filters.page = 0;
              renderUsage(container, user);
            }),
        },
        "Register usage",
      )
    : null;

  container.replaceChildren(
    h("div", { class: "page-header" }, h("h1", {}, "Lot usage"), h("div", { class: "actions" }, registerButton)),
    h("div", { class: "card" }, form, results),
  );
  await load();
}