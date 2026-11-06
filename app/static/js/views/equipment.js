import { api, downloadFile } from "../api.js";
import {
  badge,
  dataTable,
  formatDateTime,
  h,
  localDateString,
  notify,
  openModal,
} from "../ui.js";

const PAGE_SIZE = 25;
const WRITERS = ["admin", "technician"];

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

const RESULT_OPTIONS = [
  ["pass", "Pass"],
  ["fail", "Fail"],
  ["out_of_tolerance", "Out of tolerance"],
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
  return id ? renderDetail(container, user, id) : renderList(container, user);
}

function pageHeader(title, ...actions) {
  return h("div", { class: "page-header" }, h("h1", {}, title), h("div", { class: "actions" }, actions));
}

/* ---------- List ---------- */

function textFilter(label, name) {
  return h("label", {}, label, h("input", { name, value: filters[name], autocomplete: "off" }));
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

async function renderList(container, user) {
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
            renderList(container, user);
          },
        },
        "Clear",
      ),
    ),
  );

  const newButton =
    user.role === "admin"
      ? h(
          "button",
          {
            type: "button",
            class: "primary",
            onclick: () =>
              openEquipmentForm(null, (saved) => {
                location.hash = `#/equipment/${saved.id}`;
              }),
          },
          "New equipment",
        )
      : null;

  container.replaceChildren(pageHeader("Equipment", newButton), h("div", { class: "card" }, form, results));
  await load();
}

/* ---------- Forms ---------- */

async function openEquipmentForm(equipment, onSaved) {
  let users;
  try {
    users = await api("/users");
  } catch (error) {
    notify(error.message, true);
    return;
  }

  const isEdit = Boolean(equipment);
  const candidates = users.filter(
    (user) => user.is_active || (isEdit && user.username === equipment.responsible_username),
  );

  const text = (label, name, value, extra = {}) =>
    h("label", {}, label, h("input", { name, value: value ?? "", required: true, maxlength: 150, ...extra }));

  const requires = h("input", {
    type: "checkbox",
    name: "requires_calibration",
    checked: isEdit ? equipment.requires_calibration : true,
  });
  const interval = h("input", {
    type: "number",
    name: "calibration_interval_days",
    min: 1,
    max: 3650,
    value: isEdit && equipment.calibration_interval_days ? equipment.calibration_interval_days : 365,
    disabled: !requires.checked,
  });
  requires.addEventListener("change", () => {
    interval.disabled = !requires.checked;
  });

  const responsible = h(
    "select",
    { name: "responsible_username" },
    candidates.map((user) =>
      h(
        "option",
        { value: user.username, selected: isEdit && user.username === equipment.responsible_username },
        `${user.first_name} ${user.last_name} (${user.username})`,
      ),
    ),
  );

  const statusSelect = h(
    "select",
    { name: "status" },
    STATUS_OPTIONS.filter(([value]) => value).map(([value, label]) =>
      h("option", { value, selected: isEdit && equipment.status === value }, label),
    ),
  );

  const error = h("p", { class: "error", hidden: true });
  const save = h("button", { type: "submit", class: "primary" }, isEdit ? "Save changes" : "Create equipment");
  const cancel = h("button", { type: "button", onclick: () => modal.close() }, "Cancel");

  const form = h(
    "form",
    {},
    h(
      "div",
      { class: "form-grid" },
      text("Asset code", "asset_code", equipment?.asset_code, { maxlength: 50 }),
      text("Serial number", "serial_number", equipment?.serial_number, { maxlength: 100 }),
      h("label", { class: "wide" }, "Name", h("input", { name: "name", value: equipment?.name ?? "", required: true, maxlength: 150 })),
      text("Type", "equipment_type", equipment?.equipment_type, { maxlength: 100 }),
      text("Location", "location", equipment?.location, { maxlength: 100 }),
      h("label", {}, "Responsible", responsible),
      isEdit ? h("label", {}, "Status", statusSelect) : null,
      h("label", { class: "wide checkbox" }, requires, "Requires calibration"),
      h("label", { class: "wide" }, "Calibration interval (days)", interval),
    ),
    error,
    h("div", { class: "form-actions" }, cancel, save),
  );

  const modal = openModal(isEdit ? `Edit ${equipment.asset_code}` : "New equipment", form);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    save.disabled = true;

    const data = new FormData(form);
    const payload = {
      asset_code: data.get("asset_code").trim(),
      name: data.get("name").trim(),
      equipment_type: data.get("equipment_type").trim(),
      serial_number: data.get("serial_number").trim(),
      location: data.get("location").trim(),
      responsible_username: data.get("responsible_username"),
      requires_calibration: requires.checked,
    };
    if (requires.checked) payload.calibration_interval_days = Number(data.get("calibration_interval_days"));
    if (isEdit) payload.status = data.get("status");

    try {
      const saved = await api(isEdit ? `/equipment/${equipment.id}` : "/equipment", {
        method: isEdit ? "PATCH" : "POST",
        json: payload,
      });
      modal.close();
      notify(isEdit ? "Equipment updated" : "Equipment created");
      onSaved(saved);
    } catch (failure) {
      if (failure.status === 401) return;
      error.textContent = failure.message;
      error.hidden = false;
    } finally {
      save.disabled = false;
    }
  });
}

function openCalibrationForm(equipment, onSaved) {
  const today = localDateString();
  const date = h("input", { type: "date", name: "calibration_date", value: today, max: today, required: true });
  const result = h(
    "select",
    { name: "result" },
    RESULT_OPTIONS.map(([value, label]) => h("option", { value }, label)),
  );
  const file = h("input", { type: "file", accept: "application/pdf,.pdf" });
  const warning = h(
    "p",
    { class: "muted", hidden: true },
    "A failed calibration takes the equipment out of service automatically.",
  );
  result.addEventListener("change", () => {
    warning.hidden = result.value === "pass";
  });

  const error = h("p", { class: "error", hidden: true });
  const save = h("button", { type: "submit", class: "primary" }, "Register calibration");
  const cancel = h("button", { type: "button", onclick: () => modal.close() }, "Cancel");

  const form = h(
    "form",
    {},
    h("label", {}, "Calibration date", date),
    h("label", {}, "Result", result),
    warning,
    h("label", {}, "Certificate (PDF, optional)", file),
    error,
    h("div", { class: "form-actions" }, cancel, save),
  );

  const modal = openModal(`Register calibration · ${equipment.asset_code}`, form);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    save.disabled = true;

    let created;
    try {
      created = await api(`/equipment/${equipment.id}/calibrations`, {
        method: "POST",
        json: { calibration_date: date.value, result: result.value },
      });
    } catch (failure) {
      save.disabled = false;
      if (failure.status === 401) return;
      error.textContent = failure.message;
      error.hidden = false;
      return;
    }

    modal.close();

    if (file.files[0]) {
      const body = new FormData();
      body.append("file", file.files[0]);
      try {
        await api(`/equipment/${equipment.id}/calibrations/${created.id}/certificate`, {
          method: "POST",
          body,
        });
        notify("Calibration and certificate saved");
      } catch (failure) {
        notify(`Calibration saved, but the certificate was not uploaded: ${failure.message}`, true);
      }
    } else {
      notify("Calibration saved");
    }
    onSaved();
  });
}

function pickAndUpload(url, onDone) {
  const input = h("input", { type: "file", accept: "application/pdf,.pdf" });
  input.addEventListener("change", async () => {
    if (!input.files[0]) return;
    const body = new FormData();
    body.append("file", input.files[0]);
    try {
      await api(url, { method: "POST", body });
      notify("Certificate uploaded");
      onDone();
    } catch (failure) {
      if (failure.status !== 401) notify(failure.message, true);
    }
  });
  input.click();
}

/* ---------- Detail ---------- */

function field(label, value) {
  return h("div", {}, h("dt", {}, label), h("dd", {}, value));
}

function certificateCell(equipment, calibration, canWrite, refresh) {
  const url = `/equipment/${equipment.id}/calibrations/${calibration.id}/certificate`;

  if (calibration.certificate_filename) {
    return h(
      "button",
      {
        type: "button",
        class: "link",
        onclick: async () => {
          try {
            await downloadFile(url, calibration.certificate_filename);
          } catch (failure) {
            if (failure.status !== 401) notify(failure.message, true);
          }
        },
      },
      calibration.certificate_filename,
    );
  }
  if (!canWrite) return "—";
  return h("button", { type: "button", class: "small", onclick: () => pickAndUpload(url, refresh) }, "Upload PDF");
}

async function renderDetail(container, user, id) {
  const equipment = await api(`/equipment/${encodeURIComponent(id)}`);
  const [calibrations, usage] = await Promise.all([
    api(`/equipment/${equipment.id}/calibrations`, { params: { limit: 50 } }),
    api("/usage", { params: { asset_code: equipment.asset_code, limit: 10 } }),
  ]);

  const refresh = () => renderDetail(container, user, id);
  const canWrite = WRITERS.includes(user.role);
  const canCalibrate = canWrite && equipment.requires_calibration && equipment.status !== "retired";

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
            certificateCell(equipment, item, canWrite, refresh),
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

  const editButton =
    user.role === "admin"
      ? h("button", { type: "button", onclick: () => openEquipmentForm(equipment, refresh) }, "Edit")
      : null;
  const calibrateButton = canCalibrate
    ? h(
        "button",
        { type: "button", class: "primary", onclick: () => openCalibrationForm(equipment, refresh) },
        "Register calibration",
      )
    : null;

  container.replaceChildren(
    h("a", { href: "#/equipment", class: "back" }, "← Back to equipment"),
    pageHeader(`${equipment.asset_code} · ${equipment.name}`, editButton, calibrateButton),
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