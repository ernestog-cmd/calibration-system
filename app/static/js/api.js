const TOKEN_KEY = "calibration_token";

export const session = {
  get token() {
    return sessionStorage.getItem(TOKEN_KEY);
  },
  set token(value) {
    if (value) sessionStorage.setItem(TOKEN_KEY, value);
    else sessionStorage.removeItem(TOKEN_KEY);
  },
  user: null,
};

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

let onUnauthorized = () => {};

export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

function errorMessage(data, status) {
  const detail = data && data.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => `${(item.loc || []).slice(1).join(".")}: ${item.msg}`)
      .join("; ");
  }
  return `Request failed (${status})`;
}

export async function api(path, { method = "GET", params, json, form, body, auth = true } = {}) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params || {})) {
    if (value !== null && value !== undefined && value !== "") {
      url.searchParams.set(key, value);
    }
  }

  const headers = {};
  if (auth && session.token) headers.Authorization = `Bearer ${session.token}`;

  let payload;
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(json);
  } else if (form) {
    payload = new URLSearchParams(form);
  } else if (body) {
    payload = body;
  }

  let response;
  try {
    response = await fetch(url, { method, headers, body: payload });
  } catch {
    throw new ApiError(0, "Could not reach the server");
  }

  if (response.status === 401 && auth) {
    onUnauthorized();
    throw new ApiError(401, "Your session has expired");
  }

  const isJson = (response.headers.get("content-type") || "").includes("application/json");
  const data = isJson ? await response.json() : null;

  if (!response.ok) throw new ApiError(response.status, errorMessage(data, response.status));
  return data;
}

// Files need the login token, so they cannot be plain links
export async function downloadFile(path, filename) {
  let response;
  try {
    response = await fetch(path, { headers: { Authorization: `Bearer ${session.token}` } });
  } catch {
    throw new ApiError(0, "Could not reach the server");
  }

  if (response.status === 401) {
    onUnauthorized();
    throw new ApiError(401, "Your session has expired");
  }
  if (!response.ok) {
    let data = null;
    try {
      data = await response.json();
    } catch {
      // not JSON, the generic message is used
    }
    throw new ApiError(response.status, errorMessage(data, response.status));
  }

  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function login(username, password) {
  const data = await api("/auth/login", {
    method: "POST",
    form: { username, password },
    auth: false,
  });
  session.token = data.access_token;
  session.user = await api("/auth/me");
}

export function logout() {
  session.token = null;
  session.user = null;
}

export async function restoreSession() {
  if (!session.token) return false;
  try {
    session.user = await api("/auth/me");
    return true;
  } catch {
    logout();
    return false;
  }
}