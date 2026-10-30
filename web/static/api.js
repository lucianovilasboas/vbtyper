// Cliente da API v1. O navegador roda na mesma origem do backend, então o
// cookie HttpOnly acompanha as requisições automaticamente — o token nunca
// passa pelo JavaScript.

const BASE = "/api/v1";

// Respostas de erro nem sempre são JSON do backend: um proxy ou um servidor
// estático pode devolver uma página HTML (502/503). Esse HTML nunca deve virar
// mensagem de interface — o campo de status mostraria as próprias tags.
const MAX_TEXT_ERROR = 200;

function errorMessage(payload, status) {
  const detail = payload && typeof payload === "object" ? payload.error?.message : undefined;
  if (detail) return detail;
  if (typeof payload === "string") {
    const text = payload.trim();
    if (text && text.length <= MAX_TEXT_ERROR && !/<[a-z!/]/i.test(text)) return text;
  }
  return `Erro HTTP ${status}`;
}

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
    const error = new Error(errorMessage(payload, response.status));
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

  listProfiles: () => request("/profiles"),
  createProfile: (body) => request("/profiles", { method: "POST", body }),
  patchProfile: (slug, body) =>
    request(`/profiles/${encodeURIComponent(slug)}`, { method: "PATCH", body }),
  deleteProfile: (slug) =>
    request(`/profiles/${encodeURIComponent(slug)}`, { method: "DELETE" }),
  renderTranscription: (id, profile) =>
    request(`/transcriptions/${id}/render`, { method: "POST", body: { profile } }),

  createJob(file, { model, language, mode, profile, duration } = {}) {
    const form = new FormData();
    form.append("file", file, file.name || "gravacao.webm");
    if (model) form.append("model", model);
    if (language) form.append("language", language);
    if (mode) form.append("mode", mode);
    if (profile) form.append("profile", profile);
    // WebM/OGG não trazem a duração no cabeçalho: quem sabe é o cronômetro do
    // navegador. O backend só usa isto quando não consegue ler do arquivo.
    if (Number.isFinite(duration) && duration > 0) {
      form.append("duration_s", duration.toFixed(3));
    }
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
