import { api } from "./api.js";
import { notify } from "./ui.js";

const form = document.getElementById("global-search");
const input = document.getElementById("global-search-input");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const code = input.value.trim();
  if (!code) return;

  try {
    const equipment = await api(`/equipment/by-code/${encodeURIComponent(code)}`);
    input.value = "";
    input.blur();
    location.hash = `#/equipment/${equipment.id}`;
  } catch (error) {
    if (error.status === 401) return;
    notify(
      error.status === 404 ? `No equipment with code ${code.toUpperCase()}` : error.message,
      true,
    );
  }
});

// Press "/" anywhere to jump to the search box
document.addEventListener("keydown", (event) => {
  if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey) return;

  const target = event.target;
  const typing = target.matches("input, textarea, select") || target.isContentEditable;
  if (typing || document.querySelector("dialog[open]")) return;

  event.preventDefault();
  input.focus();
});