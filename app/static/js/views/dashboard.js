import { api } from "../api.js";
import { badge, h } from "../ui.js";

function dueText(alert) {
  if (alert.calibration_due_date === null) return "Never calibrated";
  if (alert.days_remaining < 0) return `Expired ${-alert.days_remaining} days ago`;
  return `Due in ${alert.days_remaining} days (${alert.calibration_due_date})`;
}

export async function renderDashboard(container) {
  const [summary, alerts] = await Promise.all([
    api("/reports/summary"),
    api("/alerts/calibrations"),
  ]);
  const state = summary.by_calibration_state;

  const stats = [
    ["Total equipment", summary.total_equipment],
    ["Valid", state.valid],
    ["Due soon", state.due_soon],
    ["Expired", state.expired],
    ["Not required", state.not_required],
    ["Out of service", summary.by_status.out_of_service],
    ["Lot usage, last 30 days", summary.usage_last_30_days],
  ];

  const attention = alerts.length
    ? h(
        "div",
        { class: "table-wrap" },
        h(
          "table",
          {},
          h(
            "thead",
            {},
            h("tr", {}, ["Equipment", "Location", "Responsible", "State", "Due"].map((t) => h("th", {}, t))),
          ),
          h(
            "tbody",
            {},
            alerts.map((alert) =>
              h(
                "tr",
                {},
                h("td", {}, `${alert.asset_code} · ${alert.name}`),
                h("td", {}, alert.location),
                h("td", {}, alert.responsible_username),
                h("td", {}, badge(alert.calibration_state)),
                h("td", {}, dueText(alert)),
              ),
            ),
          ),
        ),
      )
    : h("p", { class: "muted" }, "Nothing needs attention right now.");

  container.replaceChildren(
    h("h1", {}, "Dashboard"),
    h(
      "div",
      { class: "cards" },
      stats.map(([label, value]) =>
        h("div", { class: "card stat" }, h("div", { class: "value" }, value), h("div", { class: "label" }, label)),
      ),
    ),
    h("div", { class: "card" }, h("h2", {}, "Needs attention"), attention),
  );
}