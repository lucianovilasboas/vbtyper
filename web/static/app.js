import { api } from "./api.js";
import { Recorder } from "./recorder.js";

const $ = (id) => document.getElementById(id);

const POLL_INTERVAL_MS = 700;
const POLL_TIMEOUT_MS = 180_000;
const HISTORY_PAGE = 20;
const TERMINAL = new Set(["succeeded", "failed", "canceled"]);

const number = new Intl.NumberFormat("pt-BR");
const money = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 4,
  maximumFractionDigits: 4,
});

const recorder = new Recorder();

const state = {
  recordingStartedAt: 0,
  timerId: null,
  meterRaf: 0,
  audioContext: null,
  jobId: null,
  transcriptId: null,
  resultShownAt: 0,
  historyOffset: 0,
  historyTotal: 0,
  search: "",
  period: { days: 30, granularity: "day" },
  metric: "words",
  series: [],
};

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

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

function humanSeconds(value) {
  const seconds = Math.max(0, Number(value) || 0);
  if (seconds < 60) return `${seconds.toFixed(1).replace(".", ",")} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes} min ${String(rest).padStart(2, "0")} s`;
  return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")} min`;
}

function isoDate(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
    date.getDate()
  ).padStart(2, "0")}`;
}

function formatTimestamp(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
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
  const stream = recorder.stream;
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!stream || !AudioContextClass) return;
  state.audioContext = new AudioContextClass();
  const analyser = state.audioContext.createAnalyser();
  analyser.fftSize = 512;
  state.audioContext.createMediaStreamSource(stream).connect(analyser);
  const samples = new Uint8Array(analyser.frequencyBinCount);
  const tick = () => {
    analyser.getByteTimeDomainData(samples);
    let peak = 0;
    for (const value of samples) peak = Math.max(peak, Math.abs(value - 128) / 128);
    $("meter").style.width = `${Math.min(100, peak * 150)}%`;
    state.meterRaf = window.requestAnimationFrame(tick);
  };
  tick();
}

function stopMeter() {
  if (state.meterRaf) window.cancelAnimationFrame(state.meterRaf);
  state.meterRaf = 0;
  if (state.audioContext) state.audioContext.close().catch(() => {});
  state.audioContext = null;
  $("meter").style.width = "0";
}

function setRecordButton(recording) {
  const button = $("record");
  button.classList.toggle("recording", recording);
  button.querySelector(".record-icon").textContent = recording ? "■" : "🎙";
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
  $("cancel").hidden = false;
  setStatus("Gravando… fale normalmente.");
  startTimer();
  startMeter();
}

async function stopAndTranscribe() {
  $("record").disabled = true;
  stopTimer();
  stopMeter();
  setRecordButton(false);
  $("cancel").hidden = true;
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
  await submit(blob);
}

async function submit(blob) {
  setStatus("Enviando áudio para transcrição…", "busy");
  $("cancel").hidden = false;
  try {
    const job = await api.createJob(blob, {
      model: $("model").value,
      language: $("language").value.trim(),
    });
    state.jobId = job.id;
    const finished = await pollJob(job.id);
    handleJobResult(finished);
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    state.jobId = null;
    $("cancel").hidden = true;
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
  state.resultShownAt = performance.now();
  updateWordCount();
  $("copy").disabled = !text.trim();
  setStatus("Transcrição pronta. Revise e copie onde quiser.", "ok");
  loadHistory(true).catch(() => {});
}

async function cancelCurrent() {
  if (state.jobId) {
    setStatus("Cancelando…", "busy");
    try {
      await api.cancelJob(state.jobId);
    } catch (error) {
      setStatus(error.message, "error");
    }
    return;
  }
  if (recorder.recording) {
    recorder.cancel();
    stopMeter();
    stopTimer();
    setRecordButton(false);
    $("cancel").hidden = true;
    setStatus("Gravação descartada.");
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
    const insertMs = Math.min(Math.round(performance.now() - state.resultShownAt), 3_600_000);
    try {
      await api.patchTranscription(state.transcriptId, { inserted: true, insert_ms: insertMs });
    } catch {
      /* o registro de inserção não é crítico */
    }
  }
}

// --- configurações ----------------------------------------------------------

async function loadSettings() {
  const settings = await api.getSettings();
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
}

let languageTimer = null;
function scheduleLanguageSave() {
  if (languageTimer) window.clearTimeout(languageTimer);
  languageTimer = window.setTimeout(() => {
    const language = $("language").value.trim();
    if (language) api.patchSettings({ language }).catch(() => {});
  }, 600);
}

// --- histórico --------------------------------------------------------------

function renderItem(item) {
  const row = document.createElement("li");
  row.className = "item";

  const head = document.createElement("div");
  head.className = "item-head";

  const when = document.createElement("strong");
  when.textContent = formatTimestamp(item.created_at);
  head.append(when);

  const meta = document.createElement("span");
  meta.className = "muted";
  meta.textContent = `${item.model} · ${humanSeconds(item.duration_s)} · ${number.format(
    item.words
  )} palavras`;
  head.append(meta);

  const badge = document.createElement("span");
  if (item.error) {
    badge.className = "badge error";
    badge.textContent = "erro";
  } else if (item.inserted) {
    badge.className = "badge";
    badge.textContent = "inserido";
  }
  if (badge.textContent) head.append(badge);
  row.append(head);

  const body = document.createElement("p");
  body.className = "item-body";
  body.textContent = item.error ? item.error : item.text;
  row.append(body);

  const actions = document.createElement("div");
  actions.className = "item-actions";

  const copy = document.createElement("button");
  copy.textContent = "Copiar";
  copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(item.text);
      await api.patchTranscription(item.id, { inserted: true, insert_ms: 0 });
      setStatus("Texto do histórico copiado.", "ok");
    } catch (error) {
      setStatus(error.message, "error");
    }
  });

  const remove = document.createElement("button");
  remove.textContent = "Excluir";
  remove.addEventListener("click", async () => {
    try {
      await api.deleteTranscription(item.id);
      row.remove();
      setStatus("Registro excluído.", "ok");
    } catch (error) {
      setStatus(error.message, "error");
    }
  });

  actions.append(copy, remove);
  row.append(actions);
  return row;
}

async function loadHistory(reset = false) {
  if (reset) {
    state.historyOffset = 0;
    $("history-list").replaceChildren();
  }
  const page = await api.listTranscriptions({
    limit: HISTORY_PAGE,
    offset: state.historyOffset,
    q: state.search || undefined,
  });
  state.historyTotal = page.total;
  const list = $("history-list");
  for (const item of page.items) list.append(renderItem(item));
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

function drawChart(series) {
  const canvas = $("chart");
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth || 600;
  const height = 200;
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);

  const styles = getComputedStyle(document.documentElement);
  const brand = styles.getPropertyValue("--brand").trim() || "#4f46e5";
  const muted = styles.getPropertyValue("--muted").trim() || "#6b7280";
  const border = styles.getPropertyValue("--border").trim() || "#e3e6ef";

  const values = series.map(metricValue);
  const max = Math.max(1, ...values);
  const hasData = values.some((value) => value > 0);
  const baseline = height - 26;
  const slot = width / Math.max(1, series.length);
  const barWidth = Math.max(2, Math.min(28, slot * 0.62));

  ctx.strokeStyle = border;
  ctx.beginPath();
  ctx.moveTo(0, baseline + 0.5);
  ctx.lineTo(width, baseline + 0.5);
  ctx.stroke();

  ctx.font = "11px system-ui, sans-serif";
  ctx.textAlign = "center";

  if (!hasData) {
    ctx.fillStyle = muted;
    ctx.fillText("Sem dados no período.", width / 2, baseline - 24);
  }

  // Rótulos: múltiplos do passo e o último apenas se não colidir com o anterior.
  const step = Math.max(1, Math.ceil(series.length / 8));
  const labelIndexes = new Set();
  for (let index = 0; index < series.length; index += step) labelIndexes.add(index);
  const lastIndex = series.length - 1;
  if (lastIndex > 0 && lastIndex % step !== 0) {
    const previous = lastIndex - (lastIndex % step);
    if (lastIndex - previous >= step * 0.6) labelIndexes.add(lastIndex);
  }

  series.forEach((point, index) => {
    const value = values[index];
    const barHeight = (value / max) * (baseline - 14);
    const x = index * slot + (slot - barWidth) / 2;
    const y = baseline - barHeight;
    if (value > 0) {
      ctx.fillStyle = brand;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(x, y, barWidth, Math.max(2, barHeight), 3);
      else ctx.rect(x, y, barWidth, Math.max(2, barHeight));
      ctx.fill();
    } else {
      ctx.fillStyle = border;
      ctx.fillRect(x, baseline - 1, barWidth, 1);
    }
    if (labelIndexes.has(index)) {
      ctx.fillStyle = muted;
      ctx.fillText(point.label, index * slot + slot / 2, height - 8);
    }
  });
}

async function loadActivity() {
  const to = new Date();
  const from = new Date();
  from.setDate(from.getDate() - (state.period.days - 1));
  const data = await api.stats({
    from: isoDate(from),
    to: isoDate(to),
    granularity: state.period.granularity,
  });
  state.series = data.series;
  $("m-audio").textContent = humanSeconds(data.summary.seconds);
  $("m-words").textContent = number.format(data.summary.words);
  $("m-count").textContent = number.format(data.summary.total);
  $("m-cost").textContent = money.format(data.summary.cost_usd);
  drawChart(data.series);
  const perMinute = data.insights.words_per_minute || 0;
  const p95 = data.insights.api_p95_ms || 0;
  $("insights").textContent =
    `Ritmo médio: ${perMinute.toFixed(0)} palavras/min · Pico às ${data.insights.peak_hour}` +
    ` · p95 da API: ${number.format(p95)} ms · falhas: ${number.format(data.summary.failures)}`;
}

// --- navegação --------------------------------------------------------------

function selectView(name) {
  for (const tab of document.querySelectorAll(".tab")) {
    tab.setAttribute("aria-selected", String(tab.dataset.view === name));
  }
  for (const view of document.querySelectorAll(".view")) {
    view.hidden = view.id !== `view-${name}`;
  }
  if (name === "history") loadHistory(true).catch((error) => setStatus(error.message, "error"));
  if (name === "activity") loadActivity().catch((error) => setStatus(error.message, "error"));
}

function bindEvents() {
  $("record").addEventListener("click", () => {
    if (recorder.recording) stopAndTranscribe();
    else startRecording();
  });
  $("cancel").addEventListener("click", cancelCurrent);
  $("copy").addEventListener("click", copyTranscript);
  $("clear").addEventListener("click", () => {
    $("transcript").value = "";
    state.transcriptId = null;
    updateWordCount();
    $("copy").disabled = true;
  });
  $("transcript").addEventListener("input", updateWordCount);
  $("model").addEventListener("change", () => {
    api.patchSettings({ model: $("model").value }).catch((error) => setStatus(error.message, "error"));
  });
  $("language").addEventListener("input", scheduleLanguageSave);

  for (const tab of document.querySelectorAll(".tab")) {
    tab.addEventListener("click", () => selectView(tab.dataset.view));
  }

  let searchTimer = null;
  $("search").addEventListener("input", () => {
    if (searchTimer) window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      state.search = $("search").value.trim();
      const link = $("export-csv");
      link.href = `/api/v1/transcriptions/export.csv${state.search ? `?q=${encodeURIComponent(state.search)}` : ""}`;
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
      sibling.classList.toggle("selected", sibling === button);
    }
    state.period = { days: Number(button.dataset.days), granularity: button.dataset.granularity };
    loadActivity().catch((error) => setStatus(error.message, "error"));
  });

  $("activity-metrics").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    for (const sibling of $("activity-metrics").children) {
      sibling.classList.toggle("selected", sibling === button);
    }
    state.metric = button.dataset.metric;
    drawChart(state.series);
  });

  window.addEventListener("resize", () => drawChart(state.series));
}

async function init() {
  bindEvents();
  if (!Recorder.supported) {
    $("record").disabled = true;
    setStatus("Este navegador não oferece gravação de áudio. Use uma versão recente do Firefox ou Chrome.", "error");
  }
  try {
    const ready = await api.ready();
    setConnection(
      ready.api_key_configured ? "ok" : "warn",
      ready.api_key_configured ? "Chave configurada" : "Sem chave OpenAI"
    );
    $("key-state").textContent = ready.api_key_configured
      ? ""
      : "Nenhuma chave configurada. Rode `vb-typer-api --setup` ou salve no app desktop.";
  } catch {
    setConnection("error", "Backend indisponível");
    setStatus("Não consegui falar com o backend.", "error");
  }
  try {
    await loadSettings();
  } catch (error) {
    setStatus(error.message, "error");
  }
  loadHistory(true).catch(() => {});
}

init();
