import { api } from "../api.js";
import { badge, dataTable, h, notify, openModal } from "../ui.js";

const ROLE_OPTIONS = [
  ["admin", "Administrator"],
  ["technician", "Technician"],
  ["auditor", "Auditor"],
];

const roleLabel = (role) => (ROLE_OPTIONS.find(([value]) => value === role) || [role, role])[1];

function openUserForm(existing, onSaved) {
  const isEdit = Boolean(existing);

  const text = (label, name, value, extra = {}) =>
    h("label", {}, label, h("input", { name, value: value ?? "", required: true, maxlength: 100, autocomplete: "off", ...extra }));

  const role = h(
    "select",
    { name: "role" },
    ROLE_OPTIONS.map(([value, label]) => h("option", { value, selected: isEdit && existing.role === value }, label)),
  );

  const active = h("input", { type: "checkbox", checked: isEdit ? existing.is_active : true });

  const password = h("input", {
    name: "password",
    type: "password",
    autocomplete: "new-password",
    required: !isEdit,
    minlength: 8,
  });

  const error = h("p", { class: "error", hidden: true });
  const save = h("button", { type: "submit", class: "primary" }, isEdit ? "Save changes" : "Create user");
  const cancel = h("button", { type: "button", onclick: () => modal.close() }, "Cancel");

  const form = h(
    "form",
    {},
    h(
      "div",
      { class: "form-grid" },
      isEdit
        ? null
        : h(
            "label",
            { class: "wide" },
            "Username (letters, numbers, dot, dash and underscore)",
            h("input", { name: "username", required: true, minlength: 3, maxlength: 50, autocomplete: "off" }),
          ),
      text("First name", "first_name", existing?.first_name),
      text("Last name", "last_name", existing?.last_name),
      h("label", { class: "wide" }, "Role", role),
      h(
        "label",
        { class: "wide" },
        isEdit ? "New password (leave empty to keep the current one)" : "Password (8 characters or more)",
        password,
      ),
      isEdit ? h("label", { class: "wide checkbox" }, active, "Active (inactive users cannot sign in)") : null,
    ),
    error,
    h("div", { class: "form-actions" }, cancel, save),
  );

  const modal = openModal(isEdit ? `Edit ${existing.username}` : "New user", form);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    save.disabled = true;

    const data = new FormData(form);
    const payload = {
      first_name: data.get("first_name").trim(),
      last_name: data.get("last_name").trim(),
      role: data.get("role"),
    };
    if (isEdit) payload.is_active = active.checked;
    if (password.value) payload.password = password.value;
    if (!isEdit) payload.username = data.get("username").trim();

    try {
      await api(isEdit ? `/users/${encodeURIComponent(existing.username)}` : "/users", {
        method: isEdit ? "PATCH" : "POST",
        json: payload,
      });
      modal.close();
      notify(isEdit ? "User updated" : "User created");
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

export async function renderUsers(container, currentUser) {
  const users = await api("/users");
  const refresh = () => renderUsers(container, currentUser);

  const table = dataTable(
    ["Username", "Name", "Role", "Status", ""],
    users.map((user) => [
      user.username === currentUser.username ? `${user.username} (you)` : user.username,
      `${user.first_name} ${user.last_name}`,
      roleLabel(user.role),
      user.is_active ? badge("active") : h("span", { class: "badge badge-retired" }, "Inactive"),
      h("button", { type: "button", class: "small", onclick: () => openUserForm(user, refresh) }, "Edit"),
    ]),
  );

  container.replaceChildren(
    h(
      "div",
      { class: "page-header" },
      h("h1", {}, "Users"),
      h(
        "div",
        { class: "actions" },
        h("button", { type: "button", class: "primary", onclick: () => openUserForm(null, refresh) }, "New user"),
      ),
    ),
    h(
      "div",
      { class: "card" },
      h("p", { class: "muted" }, "Users are never deleted, only deactivated, so the history keeps its authors."),
      table,
    ),
  );
}