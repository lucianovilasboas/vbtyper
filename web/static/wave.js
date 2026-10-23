// Onda do microfone na tela Ditar.
//
// Em repouso, uma linha reta com o gradiente do demo (sem ondulação); gravando,
// o traço reage ao nível real do microfone. Sem botões: quem abre e fecha o
// microfone é o gravador. O loop de animação só roda durante a gravação e é
// pausado quando a aba Ditar não está visível.

const GRADIENT_STOPS = [
  [0.0, "#9b002f"],
  [0.12, "#d11b1b"],
  [0.25, "#ff8a00"],
  [0.38, "#f2e600"],
  [0.5, "#5edc7a"],
  [0.63, "#35d6d4"],
  [0.76, "#28a9f7"],
  [0.88, "#9c5ce0"],
  [1.0, "#f041a6"],
];

function createWaveGradient(ctx, width) {
  const gradient = ctx.createLinearGradient(0, 0, width, 0);
  for (const [stop, color] of GRADIENT_STOPS) {
    gradient.addColorStop(stop, color);
  }
  return gradient;
}

function drawIdleLine({ ctx, width, height }) {
  const centerY = height / 2;
  const gradient = createWaveGradient(ctx, width);

  ctx.clearRect(0, 0, width, height);
  ctx.beginPath();
  ctx.lineWidth = 5;
  ctx.strokeStyle = gradient;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.moveTo(0, centerY);
  ctx.lineTo(width, centerY);
  ctx.stroke();
}

function drawReactiveWave({ ctx, width, height, dataArray }) {
  const centerY = height / 2;
  const gradient = createWaveGradient(ctx, width);
  const sliceWidth = width / dataArray.length;

  ctx.clearRect(0, 0, width, height);

  ctx.beginPath();
  ctx.lineWidth = 5;
  ctx.strokeStyle = gradient;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";

  let x = 0;
  for (let i = 0; i < dataArray.length; i++) {
    const v = dataArray[i] / 128;
    const y = (v * height) / 2;

    if (i === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }

    x += sliceWidth;
  }

  ctx.stroke();

  ctx.save();
  ctx.globalAlpha = 0.2;
  ctx.beginPath();
  ctx.lineWidth = 11;
  ctx.strokeStyle = gradient;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";

  x = 0;
  for (let i = 0; i < dataArray.length; i++) {
    const v = dataArray[i] / 128;
    const y = (v * height) / 2;

    if (i === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }

    x += sliceWidth;
  }

  ctx.stroke();
  ctx.restore();

  ctx.beginPath();
  ctx.lineWidth = 1;
  ctx.strokeStyle = "rgba(0,0,0,0.08)";
  ctx.moveTo(0, centerY);
  ctx.lineTo(width, centerY);
  ctx.stroke();
}

export function createWave(canvas) {
  const ctx = canvas.getContext("2d");

  let width = 0;
  let height = 0;
  let mode = "idle";
  let tabActive = true;
  let frameId = 0;
  let audioContext = null;
  let analyser = null;
  let dataArray = null;
  let source = null;

  function measure() {
    const rect = canvas.getBoundingClientRect();
    // Aba oculta (display:none) mede 0×0: manter o último tamanho evita
    // destruir o bitmap e ter de redesenhar às cegas.
    if (rect.width < 1 || rect.height < 1) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(rect.width * dpr);
    canvas.height = Math.round(rect.height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    width = rect.width;
    height = rect.height;
    // Redimensionar zera o bitmap: parado, a linha reta precisa ser redesenhada
    // aqui; gravando, o próximo quadro cuida disso.
    if (mode === "idle") drawIdleLine({ ctx, width, height });
  }

  function frame() {
    frameId = 0;
    if (!tabActive || document.hidden) return;
    if (mode !== "live" || !analyser || !dataArray) return;

    analyser.getByteTimeDomainData(dataArray);
    drawReactiveWave({ ctx, width, height, dataArray });
    frameId = window.requestAnimationFrame(frame);
  }

  function sync() {
    if (!tabActive || document.hidden) {
      if (frameId) window.cancelAnimationFrame(frameId);
      frameId = 0;
      return;
    }
    if (mode === "live") {
      if (!frameId) frameId = window.requestAnimationFrame(frame);
    } else {
      // Parado não há animação: a linha reta é desenhada uma vez só.
      drawIdleLine({ ctx, width, height });
    }
  }

  function releaseAudio() {
    if (source) {
      source.disconnect();
      source = null;
    }
    if (audioContext) {
      audioContext.close().catch(() => {});
      audioContext = null;
    }
    analyser = null;
    dataArray = null;
  }

  function start(stream) {
    releaseAudio();
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!stream || !AudioContextClass) return;

    audioContext = new AudioContextClass();
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 2048;
    analyser.smoothingTimeConstant = 0.85;
    dataArray = new Uint8Array(analyser.fftSize);
    source = audioContext.createMediaStreamSource(stream);
    source.connect(analyser);

    mode = "live";
    sync();
  }

  function stop() {
    releaseAudio();
    mode = "idle";
    sync();
  }

  function setActive(value) {
    tabActive = Boolean(value);
    sync();
  }

  measure();
  new ResizeObserver(measure).observe(canvas);
  window.addEventListener("resize", measure);
  document.addEventListener("visibilitychange", sync);
  sync();

  return { start, stop, setActive };
}
