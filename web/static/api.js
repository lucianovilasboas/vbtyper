// Cliente da API v1. O navegador roda na mesma origem do backend, então o
// cookie HttpOnly acompanha as requisições automaticamente — o token nunca
// passa pelo JavaScript.

const BASE = "/api/v1";

async function request(path, { method = "GET", body, headers = {} } = {}) {
  const options = { method, credentials: "same-origin", headers: { ...headers } };
  if (body instanceof FormData) {
    options.body = body;
  } else if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(`${BASE}${path}`, options);
  } catch {
    throw new Error("Não foi possível falar com o backend. Ele está no ar?");
  }

  if (response.status === 204) return null;

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message =
      (payload && payload.error && payload.error.message) ||
      (typeof payload === "string" && payload) ||
      `Erro HTTP ${response.status}`;
    const error = new Error(message);
    error.code = payload && payload.error ? payload.error.code : undefined;
    error.status = response.status;
    throw error;
  }
  return payload;
}

function query(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, value);
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const api = {
  info: () => request("/info"),
  ready: () => request("/ready"),
  getSettings: () => request("/settings"),
  patchSettings: (changes) => request("/settings", { method: "PATCH", body: changes }),
  testConnection: () => request("/settings/test", { method: "POST" }),

  createJob(file, { model, language } = {}) {
    const form = new FormData();
    form.append("file", file, file.name || "gravacao.webm");
    if (model) form.append("model", model);
    if (language) form.append("language", language);
    return request("/transcription-jobs", { method: "POST", body: form });
  },
  getJob: (id) => request(`/transcription-jobs/${id}`),
  cancelJob: (id) => request(`/transcription-jobs/${id}`, { method: "DELETE" }),

  listTranscriptions: (params = {}) => request(`/transcriptions${query(params)}`),
  getTranscription: (id) => request(`/transcriptions/${id}`),
  patchTranscription: (id, changes) =>
    request(`/transcriptions/${id}`, { method: "PATCH", body: changes }),
  deleteTranscription: (id) => request(`/transcriptions/${id}`, { method: "DELETE" }),

  stats: (params = {}) => request(`/stats${query(params)}`),
};
