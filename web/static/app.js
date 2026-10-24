import { api } from "./api.js";
import { Recorder } from "./recorder.js";
import { createWave } from "./wave.js";
import { renderBars, renderHeatmap, renderLine, renderWeekdays } from "./charts.js";

const $ = (id) => document.getElementById(id);

const POLL_INTERVAL_MS = 700;
const POLL_TIMEOUT_MS = 180_000;
const HISTORY_PAGE = 25;
const TERMINAL = new Set(["succeeded", "failed", "canceled"]);
const THEME_KEY = "vb-typer-theme";
const VIEW_KEY = "vb-typer-view";
const VIEWS = new Set(["dictate", "activity", "history", "settings"]);
const REFRESH_INTERVAL_MS = 10_000;
const HEATMAP_DAYS = 91;
const UPLOAD_TYPES = new Set([
  "audio/wav",
  "audio/x-wav",
  "audio/wave",
  "audio/mpeg",
  "audio/mp4",
  "audio/x-m4a",
  "audio/m4a",
  "audio/ogg",
  "audio/webm",
]);
const UPLOAD_EXTENSIONS = [".wav", ".mp3", ".m4a", ".ogg", ".webm"];
const DEFAULT_MAX_UPLOAD_BYTES = 25 * 1024 * 1024;
const WEEKDAY_SHORT = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
const WEEKDAY_LONG = ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"];

const number = new Intl.NumberFormat("pt-BR");
const money = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 4,
  maximumFractionDigits: 4,
});

const recorder = new Recorder();
const wave = createWave($("wave"));

const state = {
  recordingStartedAt: 0,
  timerId: null,
  jobId: null,
  uploadBusy: false,
  upload: { file: null, duration: 0, previewUrl: "" },
  maxUploadBytes: DEFAULT_MAX_UPLOAD_BYTES,
  transcriptId: null,
  resultShownAt: 0,
  historyOffset: 0,
  historyTotal: 0,
  search: "",
  period: { days: 7, granularity: "day" },
  metric: "words",
  series: [],
  now: null,
  nowKey: "",
  settings: { model: "", language: "pt", week_start: "monday", allowed_models: [] },
  profiles: [],
  profileEditing: null,
  profileItems: [],
  theme: localStorage.getItem(THEME_KEY) || "auto",
  loaded: new Set(),
  view: "dictate",
  lastSeenId: null,
};

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// --- formatação -------------------------------------------------------------

function formatCost(value) {
  const amount = Number(value) || 0;
  if (amount > 0 && amount < 0.0001) return `US$ ${amount.toFixed(6)}`;
  return money.format(amount);
}

function humanSeconds(value) {
  const seconds = Math.max(0, Number(value) || 0);
  if (seconds < 60) return `${seconds.toFixed(1).replace(".", ",")} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes} min ${String(rest).padStart(2, "0")} s`;
  return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")} min`;
}

function humanMinutes(value) {
  return `${(Number(value) || 0).toFixed(1).replace(".", ",")} min`;
}

function isoDate(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
    date.getDate()
  ).padStart(2, "0")}`;
}

function fromIsoDate(text) {
  const [year, month, day] = text.split("-").map(Number);
  return new Date(year, month - 1, day);
}

/* "hoje, 18:44" · "ontem, 09:12" · "17/10, 18:44" — como no app 1.x. */
function shortStamp(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  const time = parsed.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  const today = new Date();
  const dayOf = (date) => isoDate(date);
  if (dayOf(parsed) === dayOf(today)) return `hoje, ${time}`;
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  if (dayOf(parsed) === dayOf(yesterday)) return `ontem, ${time}`;
  return `${parsed.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })}, ${time}`;
}

function setStatus(message, kind = "") {
  const node = $("status");
  node.textContent = message;
  node.dataset.state = kind;
}

function setConnection(kind, text) {
  const node = $("connection");
  node.dataset.state = kind;
  node.textContent = text;
}

// --- tema -------------------------------------------------------------------

function resolvedTheme(choice) {
  if (choice !== "auto") return choice;
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(choice, { persist = true } = {}) {
  state.theme = choice;
  document.documentElement.dataset.theme = resolvedTheme(choice);
  for (const button of document.querySelectorAll("[data-theme-choice]")) {
    button.setAttribute("aria-pressed", String(button.dataset.themeChoice === choice));
  }
  for (const button of document.querySelectorAll("[data-setting-theme]")) {
    button.setAttribute("aria-pressed", String(button.dataset.settingTheme === choice));
  }
  if (persist) localStorage.setItem(THEME_KEY, choice);
}

// --- gravação ---------------------------------------------------------------

function startTimer() {
  stopTimer();
  state.timerId = window.setInterval(() => {
    const elapsed = (performance.now() - state.recordingStartedAt) / 1000;
    $("timer").textContent = `${elapsed.toFixed(1).replace(".", ",")} s`;
  }, 100);
}

function stopTimer() {
  if (state.timerId) window.clearInterval(state.timerId);
  state.timerId = null;
}

function startMeter() {
  // A onda reage ao mesmo stream que está sendo gravado.
  if (recorder.stream) wave.start(recorder.stream);
}

function stopMeter() {
  // Sem áudio a onda volta ao repouso (o loop continua desenhando).
  wave.stop();
}

function setRecordButton(recording) {
  const button = $("record");
  button.classList.toggle("recording", recording);
  button.classList.remove("canceling");
  button.querySelector(".record-icon").textContent = recording ? "■" : "🎙";
  button.setAttribute("aria-label", recording ? "Parar e transcrever" : "Gravar");
}

function setProcessingButton() {
  const button = $("record");
  button.classList.remove("recording");
  button.classList.add("canceling");
  button.querySelector(".record-icon").textContent = "✕";
  button.setAttribute("aria-label", "Cancelar transcrição");
}

async function startRecording() {
  try {
    await recorder.open();
  } catch (error) {
    setStatus(
      error.name === "NotAllowedError"
        ? "Permissão de microfone negada. Autorize o microfone nas permissões do navegador."
        : `Não foi possível acessar o microfone: ${error.message}`,
      "error"
    );
    return;
  }
  state.transcriptId = null;
  $("transcript").value = "";
  updateWordCount();
  $("copy").disabled = true;

  recorder.begin();
  state.recordingStartedAt = performance.now();
  $("timer").textContent = "0,0 s";
  setRecordButton(true);
  setStatus("Gravando… fale normalmente.");
  startTimer();
  startMeter();
}

async function stopAndTranscribe() {
  // Medido antes de parar o gravador: é a duração real do que foi capturado.
  const recordedSeconds = (performance.now() - state.recordingStartedAt) / 1000;
  $("record").disabled = true;
  stopTimer();
  stopMeter();
  setRecordButton(false);
  setStatus("Finalizando gravação…", "busy");

  let blob;
  try {
    blob = await recorder.finish();
  } catch (error) {
    setStatus(error.message, "error");
    $("record").disabled = false;
    return;
  }
  if (!blob || !blob.size) {
    setStatus("A gravação ficou vazia. Tente novamente.", "error");
    $("record").disabled = false;
    return;
  }
  await submit(blob, recordedSeconds);
}

async function submit(blob, duration) {
  setStatus("Enviando áudio para transcrição…", "busy");
  try {
    const job = await api.createJob(blob, {
      model: state.settings.model,
      language: state.settings.language,
      profile: state.settings.default_profile,
      duration,
    });
    state.jobId = job.id;
    // Com o job em curso, o mesmo botão do microfone cancela.
    setProcessingButton();
    syncUploadControls();
    handleJobResult(await pollJob(job.id));
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    state.jobId = null;
    setRecordButton(false);
    syncUploadControls();
  }
}

const PROFILE_PHASE_TEXT = {
  revisado: "Revisando o texto…",
  email: "Montando o e-mail…",
  whatsapp: "Ajustando a mensagem…",
  programacao: "Organizando a tarefa…",
  prompt: "Montando as instruções…",
  academico: "Ajustando o texto acadêmico…",
  curriculo: "Organizando o currículo…",
  carta: "Montando a carta…",
  ata: "Montando a ata…",
};

/** Mensagem da fase atual do job, como o servidor a está executando. */
function jobPhaseText(job) {
  if (job.phase === "rendering") {
    return PROFILE_PHASE_TEXT[job.profile] || "Aplicando o perfil…";
  }
  if (job.phase === "transcribing" || job.status === "running") {
    return "Transcrevendo o áudio…";
  }
  return "Na fila…";
}

async function pollJob(jobId, { timeoutMs = POLL_TIMEOUT_MS, onStatus = setStatus } = {}) {
  const deadline = performance.now() + timeoutMs;
  for (;;) {
    const job = await api.getJob(jobId);
    if (TERMINAL.has(job.status)) return job;
    onStatus(jobPhaseText(job), "busy");
    if (performance.now() > deadline) throw new Error("Tempo limite excedido ao transcrever.");
    await sleep(POLL_INTERVAL_MS);
  }
}

/** Aplica o resultado do job na tela; ``onStatus`` separa os dois fluxos. */
function handleJobResult(job, onStatus = setStatus) {
  if (job.status === "canceled") {
    onStatus("Transcrição cancelada.");
    return;
  }
  if (job.status === "failed") {
    onStatus(job.error || "Não foi possível transcrever.", "error");
    return;
  }
  const result = job.result;
  const text = result?.text || "";
  $("transcript").value = text;
  state.transcriptId = result?.id ?? null;
  if (result?.id) state.lastSeenId = result.id;
  state.resultShownAt = performance.now();
  updateWordCount();
  $("copy").disabled = !text.trim();
  onStatus("Transcrição pronta. Revise e copie onde quiser.", "ok");
  if (result?.cost_usd) {
    onStatus(
      `Transcrição pronta · ${humanSeconds(result.duration_s)} · ${formatCost(result.cost_usd)}`,
      "ok"
    );
  }
  state.loaded.delete("history");
  state.loaded.delete("activity");
}

async function cancelJob(onStatus = setStatus) {
  if (!state.jobId) return;
  onStatus("Cancelando…", "busy");
  try {
    await api.cancelJob(state.jobId);
  } catch (error) {
    onStatus(error.message, "error");
  }
}

// --- envio de arquivo -------------------------------------------------------

let uploadSeq = 0;

function setFileStatus(message, kind = "") {
  const node = $("file-status");
  node.textContent = message;
  node.dataset.state = kind;
}

function humanBytes(bytes) {
  const value = Math.max(0, Number(bytes) || 0);
  if (value < 1024) return `${value} B`;
  const kb = value / 1024;
  if (kb < 1024) return `${kb.toFixed(1).replace(".", ",")} KB`;
  const mb = kb / 1024;
  return `${Number.isInteger(mb) ? mb : mb.toFixed(1).replace(".", ",")} MB`;
}

function isSupportedAudio(file) {
  const type = (file.type || "").split(";", 1)[0].trim().toLowerCase();
  if (UPLOAD_TYPES.has(type)) return true;
  const name = (file.name || "").toLowerCase();
  return UPLOAD_EXTENSIONS.some((extension) => name.endsWith(extension));
}

/** Duração pelos metadados do próprio arquivo; 0 quando o navegador não sabe. */
function readAudioDuration(file) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const audio = new Audio();
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      audio.removeAttribute("src");
      audio.load();
      URL.revokeObjectURL(url);
      resolve(value);
    };
    const timer = window.setTimeout(() => finish(0), 4000);
    audio.preload = "metadata";
    audio.addEventListener("loadedmetadata", () => {
      const value = audio.duration;
      finish(Number.isFinite(value) && value > 0 ? value : 0);
    });
    audio.addEventListener("error", () => finish(0));
    audio.src = url;
  });
}

/** Mantém microfone e envio coerentes: um fluxo por vez, um job por vez. */
function syncUploadControls() {
  const busy = state.uploadBusy || Boolean(state.jobId);
  const hasFile = Boolean(state.upload.file);
  $("dropzone").classList.toggle("busy", busy);
  $("dropzone").setAttribute("aria-disabled", String(busy));
  $("audio-file").disabled = busy;
  $("file-remove").disabled = busy;
  $("file-transcribe").disabled = busy || !hasFile;
  // No job do microfone o botão segue ativo: é ele que cancela.
  $("record").disabled = state.uploadBusy ? true : !Recorder.supported;
  $("file-cancel").hidden = !(state.uploadBusy && state.jobId);
}

function clearUpload({ keepStatus = false } = {}) {
  const preview = $("file-preview");
  preview.pause();
  preview.removeAttribute("src");
  preview.load();
  preview.hidden = true;
  if (state.upload.previewUrl) URL.revokeObjectURL(state.upload.previewUrl);
  state.upload = { file: null, duration: 0, previewUrl: "" };
  $("file-chip").hidden = true;
  $("file-name").textContent = "—";
  $("file-meta").textContent = "";
  $("audio-file").value = "";
  if (!keepStatus) setFileStatus("");
  syncUploadControls();
}

async function pickFile(file) {
  if (!file) return;
  if (state.uploadBusy || state.jobId) {
    setFileStatus("Espere a transcrição atual terminar.", "error");
    return;
  }
  if (recorder.recording) {
    setFileStatus("Pare a gravação antes de enviar um arquivo.", "error");
    return;
  }
  if (!isSupportedAudio(file)) {
    setFileStatus("Formato não suportado. Use WAV, MP3, M4A, OGG ou WebM.", "error");
    return;
  }
  if (!file.size) {
    setFileStatus("O arquivo está vazio.", "error");
    return;
  }
  if (file.size > state.maxUploadBytes) {
    setFileStatus(`O arquivo excede o limite de ${humanBytes(state.maxUploadBytes)}.`, "error");
    return;
  }

  const seq = ++uploadSeq;
  if (state.upload.previewUrl) URL.revokeObjectURL(state.upload.previewUrl);
  const previewUrl = URL.createObjectURL(file);
  state.upload = { file, duration: 0, previewUrl };

  $("file-chip").hidden = false;
  $("file-name").textContent = file.name || "áudio";
  $("file-meta").textContent = `${humanBytes(file.size)} · lendo a duração…`;
  $("file-transcribe").disabled = true;
  const preview = $("file-preview");
  preview.src = previewUrl;
  preview.hidden = false;
  setFileStatus("Lendo os dados do áudio…", "busy");

  const duration = await readAudioDuration(file);
  if (seq !== uploadSeq) return; // outro arquivo foi escolhido no meio
  state.upload.duration = duration;
  $("file-meta").textContent = duration
    ? `${humanBytes(file.size)} · ${humanSeconds(duration)}`
    : `${humanBytes(file.size)} · duração desconhecida`;
  // Permite escolher o mesmo arquivo outra vez depois de removê-lo.
  $("audio-file").value = "";
  setFileStatus("Arquivo pronto para transcrever.", "ok");
  syncUploadControls();
}

async function startFileJob() {
  const file = state.upload.file;
  if (!file || state.uploadBusy || state.jobId) return;
  if (recorder.recording) {
    setFileStatus("Pare a gravação antes de enviar um arquivo.", "error");
    return;
  }

  state.transcriptId = null;
  $("transcript").value = "";
  updateWordCount();
  $("copy").disabled = true;

  state.uploadBusy = true;
  syncUploadControls();
  setFileStatus("Enviando áudio para transcrição…", "busy");

  try {
    const job = await api.createJob(file, {
      model: state.settings.model,
      language: state.settings.language,
      profile: state.settings.default_profile,
      duration: state.upload.duration,
    });
    state.jobId = job.id;
    syncUploadControls();
    setFileStatus("Na fila…", "busy");
    // Arquivo longo demora: base de 10 min mais 1 min por minuto de áudio.
    const timeoutMs = Math.max(
      POLL_TIMEOUT_MS,
      600_000 + (state.upload.duration || 0) * 1000
    );
    const result = await pollJob(job.id, { timeoutMs, onStatus: setFileStatus });
    handleJobResult(result, setFileStatus);
    if (result.status === "succeeded") {
      // O áudio já está no arquivo do backend; não deixa reenviar sem querer.
      clearUpload({ keepStatus: true });
    }
  } catch (error) {
    setFileStatus(error.message, "error");
  } finally {
    state.jobId = null;
    state.uploadBusy = false;
    syncUploadControls();
  }
}

function updateWordCount() {
  const text = $("transcript").value.trim();
  const count = text ? text.split(/\s+/u).length : 0;
  $("word-count").textContent = `${number.format(count)} ${count === 1 ? "palavra" : "palavras"}`;
}

async function copyTranscript() {
  const text = $("transcript").value;
  if (!text.trim()) return;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    $("transcript").select();
    setStatus("Sem acesso à área de transferência; o texto foi selecionado.", "error");
    return;
  }
  setStatus("Texto copiado para a área de transferência.", "ok");
  if (state.transcriptId) {
    const insertMs = Math.min(
      Math.round(performance.now() - state.resultShownAt),
      3_600_000
    );
    try {
      await api.patchTranscription(state.transcriptId, { inserted: true, insert_ms: insertMs });
    } catch {
      /* registrar a inserção não é crítico */
    }
  }
}

// --- configurações ----------------------------------------------------------

const LANGUAGES = {
  pt: "Português",
  en: "Inglês",
  es: "Espanhol",
  fr: "Francês",
  it: "Italiano",
  de: "Alemão",
  ja: "Japonês",
  zh: "Chinês",
  ru: "Russo",
  ar: "Árabe",
  hi: "Hindi",
};

/** Preenche os três selects da tela Ditar e sincroniza o estado atual. */
function renderQuickSettings() {
  const model = $("quick-model");
  if (model) {
    const current = state.settings.model || "";
    model.replaceChildren();
    for (const name of state.settings.allowed_models || []) {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      model.append(option);
    }
    if (current && ![...model.options].some((option) => option.value === current)) {
      const option = document.createElement("option");
      option.value = current;
      option.textContent = current;
      model.prepend(option);
    }
    model.value = current;
  }

  const language = $("quick-language");
  if (language) {
    const current = state.settings.language || "pt";
    const codes = Object.keys(LANGUAGES);
    // Código fora da lista (posto nas Configurações) continua selecionável.
    if (!codes.includes(current)) codes.unshift(current);
    language.replaceChildren();
    for (const code of codes) {
      const option = document.createElement("option");
      option.value = code;
      option.textContent = LANGUAGES[code] ? `${LANGUAGES[code]} (${code})` : code;
      language.append(option);
    }
    language.value = current;
  }

  const profile = $("profile");
  if (profile) profile.value = state.settings.default_profile || "literal";
}

const priceFormat = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function modelLabel(name) {
  const rates = (state.settings.text_prices || {})[name];
  if (!rates) return name;
  return `${name} — ${priceFormat.format(rates[0])} / ${priceFormat.format(rates[1])} por 1M`;
}

/** Modelo de texto: o global (Configurações) e o override por perfil (editor). */
function renderSmartModelSelects() {
  const models = state.settings.allowed_smart_models || [];
  const settingsSelect = $("smart-model");
  if (settingsSelect) {
    settingsSelect.replaceChildren();
    for (const name of models) {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = modelLabel(name);
      settingsSelect.append(option);
    }
    settingsSelect.value = state.settings.smart_model || models[0] || "";
  }

  const profileSelect = $("profile-model");
  if (profileSelect) {
    const chosen = profileSelect.value;
    profileSelect.replaceChildren();
    const fallback = document.createElement("option");
    fallback.value = "";
    fallback.textContent = "padrão (usa o global)";
    profileSelect.append(fallback);
    for (const name of models) {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = modelLabel(name);
      profileSelect.append(option);
    }
    profileSelect.value = chosen;
  }
}

function renderProfileItems() {
  const host = $("profile-items");
  if (!host) return;
  host.replaceChildren();
  for (const item of state.profileItems) {
    const chip = document.createElement("span");
    chip.className = "item-chip";
    chip.textContent = item;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "×";
    remove.setAttribute("aria-label", `Remover "${item}"`);
    remove.addEventListener("click", () => {
      state.profileItems = state.profileItems.filter((entry) => entry !== item);
      renderProfileItems();
    });
    chip.append(remove);
    host.append(chip);
  }
}

function addProfileItem() {
  const input = $("profile-item-input");
  const value = input.value.trim();
  if (!value) return;
  if (value.length < 3) {
    setStatus("A regra precisa de pelo menos 3 caracteres.", "error");
    return;
  }
  if (state.profileItems.length >= 12) {
    setStatus("No máximo 12 regras por perfil.", "error");
    return;
  }
  if (!state.profileItems.includes(value)) state.profileItems.push(value);
  input.value = "";
  input.focus();
  renderProfileItems();
}

async function loadSettings() {
  const settings = await api.getSettings();
  state.settings = settings;
  const select = $("model");
  select.replaceChildren();
  for (const model of settings.allowed_models) {
    const option = document.createElement("option");
    option.value = model;
    option.textContent = model;
    select.append(option);
  }
  select.value = settings.model;
  $("language").value = settings.language;
  if ($("default-profile")) $("default-profile").value = settings.default_profile;
  renderProfileOptions();
  $("week-start").value = settings.week_start;
  renderQuickSettings();
  renderSmartModelSelects();
  renderKeyBadge(settings.api_key_configured);
}

function renderKeyBadge(configured) {
  const badge = $("key-badge");
  badge.dataset.state = configured ? "ok" : "warn";
  badge.textContent = configured ? "Configurada" : "Ausente";
  $("key-state").textContent = configured
    ? ""
    : "Nenhuma chave OpenAI configurada. Rode `vb-typer-api --setup` ou salve pelo app desktop.";
}

async function saveSetting(changes) {
  try {
    const updated = await api.patchSettings(changes);
    state.settings = { ...state.settings, ...updated };
    renderQuickSettings();
    renderSmartModelSelects();
    state.loaded.delete("activity");
    state.loaded.delete("settings");
  } catch (error) {
    setStatus(error.message, "error");
  }
}

// --- perfis de texto --------------------------------------------------------

function profileName(slug) {
  const found = state.profiles.find((profile) => profile.slug === slug);
  return found ? found.name : slug;
}

async function loadProfiles() {
  state.profiles = await api.listProfiles();
  renderProfileOptions();
  renderProfilesList();
}

function renderProfileOptions() {
  for (const id of ["profile", "default-profile"]) {
    const select = $(id);
    if (!select) continue;
    select.replaceChildren();
    for (const profile of state.profiles) {
      const option = document.createElement("option");
      option.value = profile.slug;
      option.textContent = profile.name;
      select.append(option);
    }
    select.value = state.settings.default_profile || "literal";
  }
}

function renderProfilesList() {
  const host = $("profiles-list");
  if (!host) return;
  host.replaceChildren();

  for (const profile of state.profiles) {
    const row = document.createElement("div");
    row.className = "profile-row";

    const name = document.createElement("span");
    name.className = "profile-name";
    name.textContent = profile.name;
    if (profile.builtin) {
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = "embutido";
      name.append(badge);
    }
    const meta = [];
    if (profile.model) meta.push(profile.model);
    const regras = (profile.options && profile.options.items) || [];
    if (regras.length) meta.push(`${regras.length} regra${regras.length === 1 ? "" : "s"}`);
    if (meta.length) {
      const info = document.createElement("span");
      info.className = "muted small";
      info.textContent = " · " + meta.join(" · ");
      name.append(info);
    }
    row.append(name);

    const actions = document.createElement("div");
    actions.className = "actions";

    if (state.settings.default_profile !== profile.slug) {
      const use = document.createElement("button");
      use.type = "button";
      use.textContent = "usar como padrão";
      use.addEventListener("click", async () => {
        await saveSetting({ default_profile: profile.slug });
        renderProfilesList();
      });
      actions.append(use);
    }

    const duplicate = document.createElement("button");
    duplicate.type = "button";
    duplicate.textContent = "duplicar";
    duplicate.addEventListener("click", async () => {
      try {
        await api.createProfile({
          name: `${profile.name} (cópia)`,
          instructions:
            profile.instructions ||
            "Descreva o que este perfil deve fazer com o texto ditado, sem inventar informação.",
          hint: profile.hint || null,
          options: profile.options || {},
        });
        await loadProfiles();
        setStatus("Perfil duplicado: ajuste as instruções na cópia.", "ok");
      } catch (error) {
        setStatus(error.message, "error");
      }
    });
    actions.append(duplicate);

    if (!profile.builtin) {
      const edit = document.createElement("button");
      edit.type = "button";
      edit.textContent = "editar";
      edit.addEventListener("click", () => openProfileEditor(profile));
      actions.append(edit);

      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "excluir";
      remove.addEventListener("click", async () => {
        try {
          await api.deleteProfile(profile.slug);
          if (state.settings.default_profile === profile.slug) {
            await saveSetting({ default_profile: "literal" });
          }
          await loadProfiles();
          setStatus("Perfil removido.", "ok");
        } catch (error) {
          setStatus(error.message, "error");
        }
      });
      actions.append(remove);
    }

    row.append(actions);
    host.append(row);
  }
}

function openProfileEditor(profile) {
  state.profileEditing = profile ? profile.slug : null;
  $("profile-editor").hidden = false;
  $("profile-name").value = profile ? profile.name : "";
  $("profile-instructions").value = profile ? profile.instructions : "";
  $("profile-tone").value = (profile && profile.options && profile.options.tom) || "";
  $("profile-concision").value =
    (profile && profile.options && profile.options.concisao) || "";
  $("profile-terms").checked = Boolean(
    profile && profile.options && profile.options.preservar_termos
  );
  state.profileItems = [...((profile && profile.options && profile.options.items) || [])];
  renderProfileItems();
  $("profile-model").value = (profile && profile.model) || "";
  $("profile-name").focus();
}

function closeProfileEditor() {
  state.profileEditing = null;
  $("profile-editor").hidden = true;
}

async function saveProfile() {
  const name = $("profile-name").value.trim();
  const instructions = $("profile-instructions").value.trim();
  const options = {};
  if ($("profile-tone").value) options.tom = $("profile-tone").value;
  if ($("profile-concision").value) options.concisao = $("profile-concision").value;
  if ($("profile-terms").checked) options.preservar_termos = true;
  if (state.profileItems.length) options.items = [...state.profileItems];
  if ($("profile-model").value) options.modelo = $("profile-model").value;

  try {
    if (state.profileEditing) {
      await api.patchProfile(state.profileEditing, { name, instructions, options });
    } else {
      await api.createProfile({ name, instructions, options });
    }
    closeProfileEditor();
    await loadProfiles();
    setStatus("Perfil salvo.", "ok");
  } catch (error) {
    setStatus(error.message, "error");
  }
}

let languageTimer = null;
function scheduleLanguageSave() {
  if (languageTimer) window.clearTimeout(languageTimer);
  languageTimer = window.setTimeout(() => {
    const language = $("language").value.trim().toLowerCase();
    if (language.length >= 2) saveSetting({ language });
  }, 600);
}

async function testConnection() {
  const button = $("test-connection");
  const output = $("test-result");
  button.disabled = true;
  output.textContent = "Testando…";
  try {
    const result = await api.testConnection();
    output.innerHTML = `<span class="ok-text">${result.message}</span>`;
  } catch (error) {
    output.innerHTML = `<span class="bad-text">${error.message}</span>`;
  } finally {
    button.disabled = false;
  }
}

async function loadAbout() {
  try {
    const [info, ready] = await Promise.all([api.info(), api.ready()]);
    $("about-version").textContent = `${info.app} ${info.version}`;
    $("about-paths").textContent = `Banco ${ready.database ? "ok" : "indisponível"} · ${
      info.models.length
    } modelo(s)`;
  } catch {
    $("about-version").textContent = "—";
  }
}

// --- histórico --------------------------------------------------------------

function cell(className = "") {
  const td = document.createElement("td");
  if (className) td.className = className;
  return td;
}

function historyRow(item) {
  const row = document.createElement("tr");

  const when = cell("when");
  when.textContent = shortStamp(item.created_at);
  row.append(when);

  const audio = cell("num");
  audio.textContent = item.duration_s ? humanSeconds(item.duration_s) : "—";
  audio.dataset.label = "áudio";
  row.append(audio);

  const words = cell("num");
  words.textContent = number.format(item.words);
  words.dataset.label = "palavras";
  row.append(words);

  const cost = cell("num");
  cost.textContent = item.duration_s ? formatCost(item.cost_usd) : "—";
  cost.dataset.label = "custo";
  cost.title = `tarifa de ${item.model}`;
  row.append(cost);

  const body = cell("text-cell");
  const text = document.createElement("div");
  text.className = item.error ? "empty-hint" : "text";
  text.textContent = item.error || item.text || "(sem texto)";
  body.append(text);
  if (item.mode === "smart") {
    const badge = document.createElement("span");
    badge.className = "badge smart";
    badge.textContent = "inteligente";
    body.append(badge);
  }
  if (item.inserted) {
    const badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = "inserido";
    body.append(badge);
  }
  if (item.raw_text && item.raw_text !== item.text) {
    const original = document.createElement("details");
    original.className = "raw";
    const summary = document.createElement("summary");
    summary.textContent = "ver o texto reconhecido";
    const spoken = document.createElement("p");
    spoken.className = "muted small";
    spoken.textContent = item.raw_text;
    original.append(summary, spoken);
    body.append(original);
  }
  row.append(body);

  const actions = cell();
  const group = document.createElement("div");
  group.className = "row-actions";

  const copy = document.createElement("button");
  copy.type = "button";
  copy.textContent = "Copiar";
  copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(item.text);
      await api.patchTranscription(item.id, { inserted: true, insert_ms: 0 });
      item.inserted = true;
      setStatus("Texto do histórico copiado.", "ok");
      state.loaded.delete("history");
      selectView("history");
    } catch (error) {
      setStatus(error.message, "error");
    }
  });

  const remove = document.createElement("button");
  remove.type = "button";
  remove.textContent = "Excluir";
  remove.addEventListener("click", async () => {
    try {
      await api.deleteTranscription(item.id);
      row.remove();
      setStatus("Ditado excluído do histórico.", "ok");
      state.loaded.delete("activity");
      state.loaded.delete("history");
    } catch (error) {
      setStatus(error.message, "error");
    }
  });

  const versions = document.createElement("button");
  versions.type = "button";
  versions.textContent = "Versões";
  versions.addEventListener("click", async () => {
    try {
      const existing = body.querySelector(".versions");
      if (existing) {
        existing.remove();
        return;
      }
      const detail = await api.getTranscription(item.id);
      body.append(versionToolbar(item, detail, text, row));
    } catch (error) {
      setStatus(error.message, "error");
    }
  });

  group.append(versions, copy, remove);
  actions.append(group);
  row.append(actions);
  return row;
}

/**
 * Barra da linha do histórico: alterna entre as versões já geradas e pede uma
 * nova a partir do texto reconhecido (`raw_text`, no servidor).
 */
function versionToolbar(item, detail, textEl, row) {
  const bar = document.createElement("div");
  bar.className = "versions";

  const pick = document.createElement("select");
  const literal = document.createElement("option");
  literal.value = "literal";
  literal.textContent = "Literal (original)";
  pick.append(literal);
  for (const version of detail.versions || []) {
    const option = document.createElement("option");
    option.value = String(version.id);
    option.textContent = `${profileName(version.profile)} · ${shortStamp(version.created_at)} · ${formatCost(version.cost_usd)}`;
    pick.append(option);
  }
  const last = (detail.versions || [])[(detail.versions || []).length - 1];
  pick.value = last ? String(last.id) : "literal";
  pick.addEventListener("change", () => {
    const chosen = (detail.versions || []).find((version) => String(version.id) === pick.value);
    textEl.textContent = chosen ? chosen.text : detail.raw_text || detail.text;
  });
  bar.append(pick);

  const generate = document.createElement("select");
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "gerar versão…";
  generate.append(placeholder);
  for (const profile of state.profiles) {
    if (profile.slug === "literal") continue;
    const option = document.createElement("option");
    option.value = profile.slug;
    option.textContent = profile.name;
    generate.append(option);
  }
  generate.addEventListener("change", async () => {
    if (!generate.value) return;
    const slug = generate.value;
    generate.disabled = true;
    setStatus(`Gerando versão com ${profileName(slug)}…`, "busy");
    try {
      const updated = await api.renderTranscription(item.id, slug);
      row.replaceWith(historyRow(updated));
      setStatus(`Versão gerada com ${profileName(slug)}.`, "ok");
      state.loaded.delete("activity");
    } catch (error) {
      setStatus(error.message, "error");
      generate.disabled = false;
      generate.value = "";
    }
  });
  bar.append(generate);
  return bar;
}

async function loadHistorySummary() {
  try {
    const data = await api.stats({ granularity: "day" });
    const unknown = data.summary.no_duration;
    $("history-summary").textContent =
      `${number.format(data.summary.total)} ditados · ${humanSeconds(data.summary.seconds)} de áudio` +
      ` · ${number.format(data.summary.words)} palavras · ${formatCost(data.summary.cost_usd)} estimados` +
      (unknown ? ` · ${number.format(unknown)} sem duração` : "");
  } catch {
    $("history-summary").textContent = "—";
  }
}

async function loadHistory(reset = false) {
  if (reset) {
    state.historyOffset = 0;
    $("history-body").replaceChildren();
  }
  const page = await api.listTranscriptions({
    limit: HISTORY_PAGE,
    offset: state.historyOffset,
    q: state.search || undefined,
  });
  state.historyTotal = page.total;
  const body = $("history-body");
  for (const item of page.items) body.append(historyRow(item));
  state.historyOffset += page.items.length;
  $("history-empty").hidden = state.historyOffset > 0;
  $("history-more").hidden = state.historyOffset >= state.historyTotal;
}

// --- atividade --------------------------------------------------------------

function metricValue(point) {
  if (state.metric === "count") return point.count;
  if (state.metric === "minutes") return point.seconds / 60;
  return point.words;
}

function metricFormat() {
  if (state.metric === "minutes") return humanMinutes;
  return (value) => number.format(Math.round(value));
}

function metricLabel() {
  if (state.metric === "count") return "Ditados";
  if (state.metric === "minutes") return "Tempo de áudio";
  return "Palavras ditadas";
}

function drawVolume() {
  const values = state.series.map(metricValue);
  const total = values.reduce((sum, value) => sum + value, 0);
  $("chart1-title").textContent = metricLabel();
  $("chart1-unit").textContent =
    state.metric === "minutes"
      ? humanMinutes(total)
      : `${number.format(Math.round(total))} ${state.metric === "count" ? "ditados" : "palavras"}`;
  renderBars(
    $("volume-chart"),
    values,
    state.series.map((point) => point.label),
    { format: metricFormat(), highlight: currentBucketIndex(state.period.granularity) }
  );
}

function drawPace() {
  const pace = state.series.map((point) =>
    point.seconds ? point.words / (point.seconds / 60) : 0
  );
  const peak = Math.max(0, ...pace);
  $("pace-peak").textContent = peak
    ? `pico do período: ${number.format(Math.round(peak))} palavras/min`
    : "sem dados no período";
  renderLine(
    $("pace-chart"),
    pace,
    state.series.map((point) => point.label),
    {
      format: (value) => number.format(Math.round(value)),
      unit: " palavras/min",
      highlight: currentBucketIndex(state.period.granularity),
    }
  );
}

function drawHours(data) {
  const hours = data.hours || [];
  renderBars(
    $("hours-chart"),
    hours.map((hour) => hour.count),
    hours.map((hour) => hour.label),
    {
      format: (value) => `${number.format(value)} ditado${value === 1 ? "" : "s"}`,
      highlight: nowDate().getHours(),
    }
  );
  const peak = hours.reduce(
    (top, hour) => (hour.count > top.count ? hour : top),
    hours[0] || { label: "—", count: 0 }
  );
  $("hours-peak").textContent = peak.count
    ? `pico às ${peak.label}`
    : "sem dados no período";
}

/* Últimos 91 dias, alinhados no início da semana, para as colunas fecharem. */
function heatmapCells(days, weekStart, now) {
  const end = now ? new Date(now) : new Date();
  end.setHours(0, 0, 0, 0);
  const start = new Date(end);
  start.setDate(start.getDate() - (HEATMAP_DAYS - 1));
  const wanted = weekStart === "sunday" ? 0 : 1;
  while (start.getDay() !== wanted) start.setDate(start.getDate() - 1);

  const byDate = new Map(days.map((day) => [day.bucket, day]));
  const cells = [];
  for (const cursor = new Date(start); cursor <= end; cursor.setDate(cursor.getDate() + 1)) {
    const key = isoDate(cursor);
    const day = byDate.get(key);
    const count = day ? day.count : 0;
    const level = count === 0 ? 0 : count <= 2 ? 1 : count <= 5 ? 2 : count <= 10 ? 3 : 4;
    cells.push({
      level,
      tooltip: `${WEEKDAY_SHORT[cursor.getDay()]}, ${cursor.toLocaleDateString("pt-BR", {
        day: "2-digit",
        month: "2-digit",
      })}: ${count} ditado(s)`,
      date: key,
      count,
    });
  }
  return cells;
}

function renderConsistency(days, weekStart) {
  const cells = heatmapCells(days, weekStart, state.now);
  const today = isoDate(nowDate());
  renderHeatmap($("heatmap"), cells, { today });

  const active = cells.filter((entry) => entry.count > 0).length;
  $("heat-active").textContent = number.format(active);
  const best = cells.reduce((top, entry) => (entry.count > top.count ? entry : top), { count: 0 });
  $("heat-best").textContent = best.count ? WEEKDAY_SHORT[fromIsoDate(best.date).getDay()] : "—";

  const totals = new Map();
  for (const entry of cells) {
    const weekday = fromIsoDate(entry.date).getDay();
    const current = totals.get(weekday) || { count: 0, words: 0, seconds: 0 };
    current.count += entry.count;
    current.words += (days.find((day) => day.bucket === entry.date) || {}).words || 0;
    totals.set(weekday, current);
  }
  const order = weekStart === "sunday" ? [0, 1, 2, 3, 4, 5, 6] : [1, 2, 3, 4, 5, 6, 0];
  const weekdays = order.map((weekday) => ({
    label: WEEKDAY_SHORT[weekday],
    count: (totals.get(weekday) || { count: 0 }).count,
    words: (totals.get(weekday) || { words: 0 }).words,
  }));
  renderWeekdays($("weekday-chart"), weekdays, {
    highlight: WEEKDAY_SHORT[nowDate().getDay()],
  });
  const busiest = weekdays.reduce((top, day) => (day.count > top.count ? day : top), weekdays[0]);
  $("weekday-peak").textContent = busiest.count
    ? `mais uso: ${WEEKDAY_LONG[order[weekdays.indexOf(busiest)]]}`
    : "sem dados no período";
}

function renderInsights(data) {
  const insights = data.insights;
  const parts = [
    `Ritmo médio: ${number.format(Math.round(insights.words_per_minute))} palavras/min`,
    `duração média: ${humanSeconds(insights.average_duration)}`,
    `pico às ${insights.peak_hour}`,
    `p95 da API: ${number.format(insights.api_p95_ms)} ms`,
    `falhas: ${number.format(data.summary.failures)}`,
  ];
  if (data.summary.no_duration) {
    parts.push(`${number.format(data.summary.no_duration)} sem duração`);
  }
  $("insights").textContent = parts.join(" · ");
}

function renderMetrics(data) {
  const summary = data.summary;
  const insights = data.insights;
  $("m-audio").textContent = humanSeconds(summary.seconds);
  $("m-audio-sub").textContent = `${number.format(Math.round(insights.average_duration))} s por ditado`;
  $("m-words").textContent = number.format(summary.words);
  $("m-words-sub").textContent = `${number.format(Math.round(insights.words_per_minute))} palavras/min`;
  $("m-count").textContent = number.format(summary.total);
  $("m-count-sub").textContent = summary.not_inserted
    ? `${number.format(summary.not_inserted)} sem inserir`
    : "todos inseridos";
  $("m-cost").textContent = formatCost(summary.cost_usd);
  $("m-cost-sub").textContent = summary.total
    ? `${formatCost(summary.cost_usd / summary.total)} por ditado`
    : "—";
}

/** "Agora" segundo o servidor (as datas do histórico são do fuso dele). */
function nowDate() {
  return state.now ? new Date(state.now) : new Date();
}

/** Chave do relógio do navegador, só para detectar a virada de hora/dia. */
function clockKey() {
  const date = new Date();
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}-${date.getHours()}`;
}

/** Índice do balde atual na série (hoje ou o mês corrente). */
function currentBucketIndex(granularity) {
  const iso = isoDate(nowDate());
  const key = granularity === "month" ? iso.slice(0, 7) : iso;
  return state.series.findIndex((point) => point.bucket === key);
}

function renderNowCaption() {
  const target = $("now-caption");
  if (!target) return;
  const date = nowDate();
  const day = String(date.getDate()).padStart(2, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const hour = String(date.getHours()).padStart(2, "0");
  target.textContent = `agora: ${WEEKDAY_LONG[date.getDay()]}, ${day}/${month} · ${hour}h`;
}

async function loadActivity() {
  const to = new Date();
  const from = new Date();
  from.setDate(from.getDate() - (state.period.days - 1));
  const heatFrom = new Date();
  heatFrom.setDate(heatFrom.getDate() - (HEATMAP_DAYS - 1));

  const [data, daily] = await Promise.all([
    api.stats({ from: isoDate(from), to: isoDate(to), granularity: state.period.granularity }),
    api.stats({ from: isoDate(heatFrom), to: isoDate(to), granularity: "day" }),
  ]);

  state.series = data.series;
  state.now = data.now;
  state.nowKey = clockKey();
  $("period-caption").textContent = `nos últimos ${state.period.days} dias`;
  renderNowCaption();
  renderMetrics(data);
  drawVolume();
  drawPace();
  drawHours(data);
  renderConsistency(daily.series, state.settings.week_start);
  renderInsights(data);
}

// --- navegação --------------------------------------------------------------

function selectView(name) {
  const view = VIEWS.has(name) ? name : "dictate";
  state.view = view;
  localStorage.setItem(VIEW_KEY, view);

  wave.setActive(view === "dictate");
  for (const tab of document.querySelectorAll(".nav button")) {
    tab.setAttribute("aria-selected", String(tab.dataset.view === view));
  }
  for (const section of document.querySelectorAll(".view")) {
    section.classList.toggle("active", section.id === `view-${view}`);
  }
  const loaders = { history: loadHistoryTab, activity: loadActivityTab, settings: loadSettingsTab };
  const loader = loaders[view];
  if (loader) loader();
}

function loadHistoryTab() {
  if (state.loaded.has("history")) return;
  state.loaded.add("history");
  loadHistorySummary().catch(() => {});
  loadHistory(true).catch((error) => setStatus(error.message, "error"));
}

function loadActivityTab() {
  if (state.loaded.has("activity")) return;
  state.loaded.add("activity");
  loadActivity().catch((error) => setStatus(error.message, "error"));
}

function loadSettingsTab() {
  if (state.loaded.has("settings")) return;
  state.loaded.add("settings");
  loadSettings().catch((error) => setStatus(error.message, "error"));
  loadProfiles().catch((error) => setStatus(error.message, "error"));
  loadAbout();
}

// --- atualização automática -------------------------------------------------

/**
 * Checa de tempos em tempos se chegou ditado novo (de qualquer cliente: este
 * navegador, o desktop, outro aparelho) e atualiza a tela ativa.
 *
 * Polling em vez de WebSocket/SSE: o projeto já é baseado em polling, não ganha
 * dependência, atravessa o Traefik sem estado de conexão e o worker roda num
 * processo só — um fluxo de eventos seria peça nova sem ganho real aqui.
 */
async function checkNewDictations() {
  if (document.hidden || recorder.recording || state.jobId) return;
  // Virada de hora/dia: o destaque de "agora" precisa se mover.
  if (state.view === "activity" && state.nowKey && clockKey() !== state.nowKey) {
    state.nowKey = clockKey();
    loadActivity();
    return;
  }

  let newest;
  try {
    // A lista vem ordenada por id desc: a primeira linha é o ditado mais recente.
    const page = await api.listTranscriptions({ limit: 1 });
    newest = page.items?.[0]?.id ?? null;
  } catch {
    return; // checagem de fundo: falha silenciosa, tenta de novo no próximo ciclo
  }

  if (state.lastSeenId === null) {
    state.lastSeenId = newest;
    return;
  }
  if (newest === state.lastSeenId) return;
  state.lastSeenId = newest;

  // Quem já pediu "carregar mais" não é atropelado: recarregamos só a primeira
  // página (25 linhas). `historyOffset` conta linhas, não páginas.
  if (state.view === "history" && state.historyOffset > HISTORY_PAGE) return;

  state.loaded.delete("history");
  state.loaded.delete("activity");
  if (state.view === "history") loadHistoryTab();
  else if (state.view === "activity") loadActivityTab();
}

function startAutoRefresh() {
  const tick = () => {
    checkNewDictations().finally(() => {
      window.setTimeout(tick, REFRESH_INTERVAL_MS);
    });
  };
  window.setTimeout(tick, REFRESH_INTERVAL_MS);

  // Ao voltar para a aba, não espera o próximo ciclo.
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) checkNewDictations();
  });
}

// --- PWA (instalação) -------------------------------------------------------

const INSTALL_DISMISSED_KEY = "vb-typer-install-dismissed";

function hideInstall() {
  const banner = $("install-banner");
  if (banner) banner.hidden = true;
}

function setupPwa() {
  if ("serviceWorker" in navigator) {
    // Só em contexto seguro (https ou localhost) o navegador registra o worker.
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    });
  }

  const banner = $("install-banner");
  const confirm = $("install-confirm");
  const dismiss = $("install-dismiss");
  const help = $("install-help");
  if (!banner || !confirm || !dismiss) return;

  const dismissed = () => localStorage.getItem(INSTALL_DISMISSED_KEY) === "1";
  let promptEvent = null;

  dismiss.addEventListener("click", () => {
    localStorage.setItem(INSTALL_DISMISSED_KEY, "1");
    hideInstall();
  });

  confirm.addEventListener("click", async () => {
    if (!promptEvent) return;
    promptEvent.prompt();
    const choice = await promptEvent.userChoice;
    promptEvent = null;
    if (choice.outcome === "accepted") hideInstall();
  });

  window.addEventListener("appinstalled", () => {
    localStorage.setItem(INSTALL_DISMISSED_KEY, "1");
    hideInstall();
  });

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    promptEvent = event;
    if (!dismissed()) banner.hidden = false;
  });

  // O iOS não emite `beforeinstallprompt`: lá o caminho é o menu Compartilhar.
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
  const standalone =
    window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  if (ios && !standalone && !dismissed()) {
    confirm.hidden = true;
    help.textContent = "No Safari: Compartilhar → Adicionar à Tela de Início.";
    banner.hidden = false;
  }
}

function bindEvents() {
  $("record").addEventListener("click", () => {
    if (recorder.recording) {
      stopAndTranscribe();
    } else if (state.jobId) {
      cancelJob();
    } else {
      startRecording();
    }
  });
  $("copy").addEventListener("click", copyTranscript);

  const dropzone = $("dropzone");
  const pickerOpen = () => !state.uploadBusy && !state.jobId;
  dropzone.addEventListener("click", () => {
    if (pickerOpen()) $("audio-file").click();
  });
  dropzone.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    if (pickerOpen()) $("audio-file").click();
  });
  for (const type of ["dragenter", "dragover"]) {
    dropzone.addEventListener(type, (event) => {
      event.preventDefault();
      if (pickerOpen()) dropzone.classList.add("dragging");
    });
  }
  dropzone.addEventListener("dragleave", (event) => {
    if (!dropzone.contains(event.relatedTarget)) dropzone.classList.remove("dragging");
  });
  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropzone.classList.remove("dragging");
    const files = [...(event.dataTransfer?.files || [])];
    if (!files.length) return;
    if (files.length > 1) setFileStatus("Um arquivo por vez: usando o primeiro.");
    pickFile(files[0]).catch((error) => setFileStatus(error.message, "error"));
  });
  $("audio-file").addEventListener("change", () => {
    const file = $("audio-file").files?.[0];
    if (file) pickFile(file).catch((error) => setFileStatus(error.message, "error"));
  });
  $("file-remove").addEventListener("click", clearUpload);
  $("file-transcribe").addEventListener("click", () => {
    startFileJob().catch((error) => setFileStatus(error.message, "error"));
  });
  $("file-cancel").addEventListener("click", () => cancelJob(setFileStatus));
  $("clear").addEventListener("click", () => {
    $("transcript").value = "";
    state.transcriptId = null;
    updateWordCount();
    $("copy").disabled = true;
  });
  $("transcript").addEventListener("input", updateWordCount);
  $("go-settings").addEventListener("click", () => selectView("settings"));

  for (const tab of document.querySelectorAll(".nav button")) {
    tab.addEventListener("click", () => selectView(tab.dataset.view));
  }

  for (const button of document.querySelectorAll("[data-theme-choice]")) {
    button.addEventListener("click", () => applyTheme(button.dataset.themeChoice));
  }
  for (const button of document.querySelectorAll("[data-setting-theme]")) {
    button.addEventListener("click", () => applyTheme(button.dataset.settingTheme));
  }
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (state.theme === "auto") applyTheme("auto", { persist: false });
  });

  let searchTimer = null;
  $("search").addEventListener("input", () => {
    if (searchTimer) window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      state.search = $("search").value.trim();
      const filtered = `/api/v1/transcriptions/export.csv${
        state.search ? `?q=${encodeURIComponent(state.search)}` : ""
      }`;
      $("export-csv-filtered").hidden = !state.search;
      $("export-csv-filtered").href = filtered;
      loadHistory(true).catch((error) => setStatus(error.message, "error"));
    }, 300);
  });
  $("history-more").addEventListener("click", () =>
    loadHistory(false).catch((error) => setStatus(error.message, "error"))
  );

  $("activity-periods").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    for (const sibling of $("activity-periods").children) {
      sibling.setAttribute("aria-pressed", String(sibling === button));
    }
    state.period = { days: Number(button.dataset.days), granularity: button.dataset.granularity };
    loadActivity().catch((error) => setStatus(error.message, "error"));
  });

  $("activity-metrics").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    for (const sibling of $("activity-metrics").children) {
      sibling.setAttribute("aria-pressed", String(sibling === button));
    }
    state.metric = button.dataset.metric;
    drawVolume();
  });

  $("model").addEventListener("change", () => saveSetting({ model: $("model").value }));
  $("quick-model").addEventListener("change", () =>
    saveSetting({ model: $("quick-model").value })
  );
  $("quick-language").addEventListener("change", () =>
    saveSetting({ language: $("quick-language").value })
  );
  $("profile").addEventListener("change", async () => {
    await saveSetting({ default_profile: $("profile").value });
    renderProfilesList();
    state.loaded.delete("history");
  });
  $("default-profile").addEventListener("change", async () => {
    await saveSetting({ default_profile: $("default-profile").value });
    renderProfilesList();
    state.loaded.delete("history");
  });
  $("smart-model").addEventListener("change", () =>
    saveSetting({ smart_model: $("smart-model").value })
  );
  $("profile-new").addEventListener("click", () => openProfileEditor(null));
  $("profile-item-add").addEventListener("click", addProfileItem);
  $("profile-item-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      addProfileItem();
    }
  });
  $("profile-cancel").addEventListener("click", closeProfileEditor);
  $("profile-save").addEventListener("click", saveProfile);
  $("language").addEventListener("input", scheduleLanguageSave);
  $("week-start").addEventListener("change", async () => {
    await saveSetting({ week_start: $("week-start").value });
    state.loaded.delete("activity");
  });
  $("test-connection").addEventListener("click", testConnection);

  for (const item of document.querySelectorAll(".side-item")) {
    item.addEventListener("click", () => {
      for (const sibling of document.querySelectorAll(".side-item")) {
        sibling.setAttribute("aria-current", String(sibling === item));
      }
      const section = $(item.dataset.section);
      if (section) section.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }
}

async function init() {
  applyTheme(state.theme, { persist: false });
  bindEvents();
  setupPwa();

  // A aba escolhida sobrevive à recarga; sem escolha anterior, começa em Ditar.
  selectView(localStorage.getItem(VIEW_KEY) || "dictate");
  startAutoRefresh();

  if (!Recorder.supported) {
    $("record").disabled = true;
    setStatus(
      "Este navegador não grava áudio pelo microfone. Você ainda pode enviar um arquivo abaixo.",
      "error"
    );
  }
  syncUploadControls();

  try {
    const ready = await api.ready();
    setConnection(
      ready.api_key_configured ? "ok" : "warn",
      ready.api_key_configured ? "Chave configurada" : "Sem chave OpenAI"
    );
    renderKeyBadge(ready.api_key_configured);
  } catch {
    setConnection("error", "Backend indisponível");
    setStatus("Não consegui falar com o backend.", "error");
  }

  try {
    const info = await api.info();
    const limit = Number(info.max_upload_bytes);
    if (Number.isFinite(limit) && limit > 0) state.maxUploadBytes = limit;
    $("upload-hint").textContent =
      `WAV, MP3, M4A, OGG ou WebM · até ${humanBytes(state.maxUploadBytes)}`;
  } catch {
    /* o limite padrão do cliente continua valendo */
  }

  try {
    // Carrega os valores efetivos para os chips da tela Ditar; a tela de
    // configurações recarrega e completa com o "Sobre" quando for aberta.
    await loadSettings();
    await loadProfiles();
  } catch (error) {
    setStatus(error.message, "error");
  }
}

init();
