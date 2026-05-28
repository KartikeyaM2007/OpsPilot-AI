const API_BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export async function apiGet(path) {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`GET ${path} failed`);
  }
  return response.json();
}

export async function apiPost(path, body = null) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : null,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `POST ${path} failed`);
  }

  return response.json();
}

export async function apiPut(path, body = null) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : null,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `PUT ${path} failed`);
  }

  return response.json();
}

export async function apiDelete(path) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `DELETE ${path} failed`);
  }

  return response.json();
}
