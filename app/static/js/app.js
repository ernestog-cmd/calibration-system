import { ApiError, login, logout, restoreSession, session, setUnauthorizedHandler } from "./api.js";
import { h } from "./ui.js";
import { renderAlerts } from "./views/alerts.js";
import { renderAudit } from "./views/audit.js";
import { renderDashboard } from "./views/dashboard.js";
import { renderEquipment } from "./views/equipment.js";
import { renderReports } from "./views/reports.js";
import { renderUsage } from "./views/usage.js";
import { renderUsers } from "./views/users.js";

const NAV = [
  { key: "dashboard", label: "Dashboard", render: renderDashboard },
  { key: "equipment", label: "Equipment", render: renderEquipment },
  { key: "usage", label: "Lot usage", render: renderUsage },
  { key: "alerts", label: "Alerts", render: renderAlerts },
  { key: "reports", label: "Reports", render: renderReports },
  { key: "audit", label: "Audit log", render: renderAudit, roles: ["admin", "auditor"] },
  { key: "users", label: "Users", render: renderUsers, roles: ["admin"] },
];

const loginView = document.getElementById("login-view");
const appView = document.getElementById("app-view");
const loginForm = document.getElementById("login-form");
const loginError = document.getElementById("login-error");
const loginButton = document.getElementById("login-button");
const usernameInput = document.getElementById("login-username");
const passwordInput = document.getElementById("login-password");
const nav = document.getElementById("nav");
const view = document.getElementById("view");
const userInfo = document.getElementById("user-info");

function allowed(item) {
  return !item.roles || item.roles.includes(session.user.role);
}

function safeDecode(part) {
  try {
    return decodeURIComponent(part);
  } catch {
    return part;
  }
}

function route() {
  const parts = location.hash.replace(/^#\//, "").split("/").filter(Boolean).map(safeDecode);
  return { key: parts[0] || "dashboard", args: parts.slice(1) };
}

function renderNav() {
  const { key } = route();
  nav.replaceChildren(
    ...NAV.filter(allowed).map((item) =>
      h("a", { href: `#/${item.key}`, class: item.key === key ? "active" : null }, item.label),
    ),
  );
}

function message(title, text, isError = false) {
  return h("div", { class: "card" }, h("h1", {}, title), h("p", { class: isError ? "error" : "muted" }, text));
}

async function renderRoute() {
  if (!session.user) return;
  renderNav();

  const { key, args } = route();
  const item = NAV.find((entry) => entry.key === key);
  if (!item) return view.replaceChildren(message("Page not found", "That page does not exist."));
  if (!allowed(item)) {
    return view.replaceChildren(message(item.label, "You do not have access to this page.", true));
  }
  if (!item.render) return view.replaceChildren(message(item.label, "Coming soon."));

  // Each render gets its own container, so a slow request can never overwrite a newer page
  const container = h("div");
  view.replaceChildren(container);
  container.append(h("p", { class: "muted" }, "Loading..."));

  try {
    await item.render(container, session.user, args);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return;
    container.replaceChildren(message(item.label, error.message, true));
  }
}

function showLogin(notice = "") {
  appView.hidden = true;
  loginView.hidden = false;
  loginError.hidden = !notice;
  loginError.textContent = notice;
  passwordInput.value = "";
  usernameInput.focus();
}

function showApp() {
  loginView.hidden = true;
  appView.hidden = false;
  userInfo.textContent = `${session.user.first_name} ${session.user.last_name} (${session.user.role})`;
  if (!location.hash) location.hash = "#/dashboard";
  renderRoute();
}

setUnauthorizedHandler(() => {
  logout();
  showLogin("Your session has expired. Please sign in again.");
});

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginButton.disabled = true;
  loginError.hidden = true;
  try {
    await login(usernameInput.value.trim(), passwordInput.value);
    showApp();
  } catch (error) {
    loginError.textContent = error.message;
    loginError.hidden = false;
  } finally {
    loginButton.disabled = false;
  }
});

document.getElementById("logout-button").addEventListener("click", () => {
  logout();
  location.hash = "";
  showLogin();
});

window.addEventListener("hashchange", renderRoute);

(await restoreSession()) ? showApp() : showLogin();