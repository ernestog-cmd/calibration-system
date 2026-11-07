import { api } from "../api.js";
import { badge, dataTable, h, notify } from "../ui.js";

function dueText(alert) {
  if (alert.calibration_due_date === null) return "Never calibrated";
  if (alert.days_remaining < 0) return `Expired ${-alert.days_remaining} days ago`;
  return `Due in ${alert.days_remaining} days (${alert.calibration_due_date})`;
}

async function openByCode(code) {
  try {
    const equipment = await api(`/equipment/by-code/${encodeURIComponent(code)}`);
    location.hash = `#/equipment/${equipment.id}`;
  } catch (error) {
    if (error.status !== 401) notify(error.message, true);
  }
}

async function runDigest(event) {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const result = await api("/alerts/run", { method: "POST" });
    if (result.error) notify(result.error, true);
    else if (result.expired + result.due_soon === 0) notify("Nothing to report right now");
    else if (result.email_sent) notify("Digest sent by email");
    else notify("Digest generated (email is not configured, so it was only logged)");
  } catch (error) {
    if (error.status !== 401) notify(error.message, true);
  } finally {
    button.disabled = false;
  }
}

export async function renderAlerts(container, user) {
  const alerts = await api("/alerts/calibrations");
  const expired = alerts.filter((alert) => alert.calibration_state === "expired").length;
  const dueSoon = alerts.length - expired;

  const runButton =
    user.role === "admin"
      ? h("button", { type: "button", class: "primary", onclick: runDigest }, "Run digest now")
      : null;

  const content = alerts.length
    ? dataTable(
        ["Equipment", "Location", "Responsible", "Status", "Calibration", "Due"],
        alerts.map((alert) => [
          h(
            "button",
            { type: "button", class: "link", onclick: () => openByCode(alert.asset_code) },
            `${alert.asset_code} · ${alert.name}`,
          ),
          alert.location,
          alert.responsible_username,
          badge(alert.status),
          badge(alert.calibration_state),
          dueText(alert),
        ]),
      )
    : h("p", { class: "muted" }, "Nothing needs attention right now.");

  container.replaceChildren(
    h("div", { class: "page-header" }, h("h1", {}, "Alerts"), h("div", { class: "actions" }, runButton)),
    h(
      "div",
      { class: "card" },
      h("p", { class: "muted" }, `${expired} expired · ${dueSoon} due soon. Retired equipment is not listed.`),
      content,
    ),
  );
}