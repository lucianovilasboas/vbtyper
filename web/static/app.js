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
const WEEKDAY_SHORT = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
const WEEKDAY_LONG = ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"];
const MODE_LABEL = { literal: "Literal", smart: "Inteligente" };
const MODE_HELP = {
  literal: "Literal entrega exatamente o que foi reconhecido.",
  smart: "Inteligente ajusta datas, números, valores e siglas (18/10/2025, R$ 50,20, 30%).",
};

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
  transcriptId: null,
  resultShownAt: 0,
  historyOffset: 0,
  historyTotal: 0,
  search: "",
  period: { days: 30, granularity: "day" },
  metric: "words",
  series: [],
  settings: { model: "", language: "pt", week_start: "monday", allowed_models: [] },
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
      mode: state.settings.mode,
      duration,
    });
    state.jobId = job.id;
    // Com o job em curso, o mesmo botão do microfone cancela.
    setProcessingButton();
    $("record").disabled = false;
    handleJobResult(await pollJob(job.id));
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    state.jobId = null;
    setRecordButton(false);
    $("record").disabled = false;
  }
}

async function pollJob(jobId) {
  const deadline = performance.now() + POLL_TIMEOUT_MS;
  for (;;) {
    const job = await api.getJob(jobId);
    if (TERMINAL.has(job.status)) return job;
    setStatus(job.status === "running" ? "Transcrevendo…" : "Na fila…", "busy");
    if (performance.now() > deadline) throw new Error("Tempo limite excedido ao transcrever.");
    await sleep(POLL_INTERVAL_MS);
  }
}

function handleJobResult(job) {
  if (job.status === "canceled") {
    setStatus("Transcrição cancelada.");
    return;
  }
  if (job.status === "failed") {
    setStatus(job.error || "Não foi possível transcrever.", "error");
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
  setStatus("Transcrição pronta. Revise e copie onde quiser.", "ok");
  if (result?.cost_usd) {
    setStatus(
      `Transcrição pronta · ${humanSeconds(result.duration_s)} · ${formatCost(result.cost_usd)}`,
      "ok"
    );
  }
  state.loaded.delete("history");
  state.loaded.delete("activity");
}

async function cancelJob() {
  if (!state.jobId) return;
  setStatus("Cancelando…", "busy");
  try {
    await api.cancelJob(state.jobId);
  } catch (error) {
    setStatus(error.message, "error");
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

function renderSettingChips() {
  $("chip-model").textContent = state.settings.model || "—";
  $("chip-language").textContent = state.settings.language || "—";
  $("chip-mode").textContent = MODE_LABEL[state.settings.mode] || state.settings.mode || "—";
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
  $("mode").value = settings.mode;
  $("mode-help").textContent = MODE_HELP[settings.mode] || MODE_HELP.literal;
  $("week-start").value = settings.week_start;
  renderSettingChips();
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
    renderSettingChips();
    if (updated.mode) $("mode-help").textContent = MODE_HELP[updated.mode] || MODE_HELP.literal;
    state.loaded.delete("activity");
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
  row.append(audio);

  const words = cell("num");
  words.textContent = number.format(item.words);
  row.append(words);

  const cost = cell("num");
  cost.textContent = item.duration_s ? formatCost(item.cost_usd) : "—";
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

  group.append(copy, remove);
  actions.append(group);
  row.append(actions);
  return row;
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
    { format: metricFormat() }
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
    { format: (value) => number.format(Math.round(value)), unit: " palavras/min" }
  );
}

/* Últimos 91 dias, alinhados no início da semana, para as colunas fecharem. */
function heatmapCells(days, weekStart) {
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  start.setDate(start.getDate() - (HEATMAP_DAYS - 1));
  const wanted = weekStart === "sunday" ? 0 : 1;
  while (start.getDay() !== wanted) start.setDate(start.getDate() - 1);

  const byDate = new Map(days.map((day) => [day.bucket, day]));
  const cells = [];
  for (const cursor = new Date(start); cursor <= new Date(); cursor.setDate(cursor.getDate() + 1)) {
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
  const cells = heatmapCells(days, weekStart);
  renderHeatmap($("heatmap"), cells);

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
  renderWeekdays($("weekday-chart"), weekdays);
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
  $("period-caption").textContent = `nos últimos ${state.period.days} dias`;
  renderMetrics(data);
  drawVolume();
  drawPace();
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
  $("mode").addEventListener("change", async () => {
    await saveSetting({ mode: $("mode").value });
    state.loaded.delete("history");
  });
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

  // A aba escolhida sobrevive à recarga; sem escolha anterior, começa em Ditar.
  selectView(localStorage.getItem(VIEW_KEY) || "dictate");
  startAutoRefresh();

  if (!Recorder.supported) {
    $("record").disabled = true;
    setStatus(
      "Este navegador não oferece gravação de áudio. Use uma versão recente do Firefox ou Chrome.",
      "error"
    );
  }

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
    // Carrega os valores efetivos para os chips da tela Ditar; a tela de
    // configurações recarrega e completa com o "Sobre" quando for aberta.
    await loadSettings();
  } catch (error) {
    setStatus(error.message, "error");
  }
}

init();
