/* Gráficos das telas de atividade — SVG puro, sem biblioteca e sem build.
   A geometria é a do protótipo do 1.x: viewBox 780x205, três linhas de grade,
   rótulos de eixo discretos. */

const NS = "http://www.w3.org/2000/svg";
const WIDTH = 780;
const HEIGHT = 205;
const LEFT = 42;
const RIGHT = 8;
const TOP = 16;
const BOTTOM = 28;
const PLOT_HEIGHT = HEIGHT - TOP - BOTTOM;

function node(name, attributes = {}) {
  const element = document.createElementNS(NS, name);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
  return element;
}

function label(text, x, y, anchor = "middle") {
  const element = node("text", { class: "axis-label", x, y, "text-anchor": anchor });
  element.textContent = text;
  return element;
}

/* Rótulos do eixo X: alguns múltiplos do passo, e o último se não colidir. */
function tickIndexes(count, wanted = 6) {
  const step = Math.max(1, Math.ceil(count / wanted));
  const chosen = new Set();
  for (let index = 0; index < count; index += step) chosen.add(index);
  const last = count - 1;
  if (last > 0 && last % step !== 0 && last - (last % step) >= step * 0.6) chosen.add(last);
  return chosen;
}

function grid(svg, maximum, format) {
  svg.replaceChildren();
  for (let step = 0; step <= 3; step += 1) {
    const y = TOP + (PLOT_HEIGHT * step) / 3;
    svg.append(node("line", { class: "gridline", x1: LEFT, y1: y, x2: WIDTH - RIGHT, y2: y }));
    svg.append(label(format(maximum * (1 - step / 3)), LEFT - 8, y + 3, "end"));
  }
}

export function renderBars(svg, values, labels, { format = String, highlight = -1 } = {}) {
  const maximum = Math.max(1, ...values);
  grid(svg, maximum, format);
  const slot = (WIDTH - LEFT - RIGHT) / Math.max(1, values.length);
  const width = Math.max(3, Math.min(24, slot * 0.58));
  const ticks = tickIndexes(values.length);

  values.forEach((value, index) => {
    const isNow = index === highlight;
    if (value > 0) {
      const height = Math.max(2, (value / maximum) * PLOT_HEIGHT);
      const x = LEFT + slot * index + (slot - width) / 2;
      const y = TOP + PLOT_HEIGHT - height;
      const bar = node("rect", { class: isNow ? "bar now" : "bar", x, y, width, height, rx: 3 });
      const tooltip = node("title");
      tooltip.textContent = `${labels[index]}: ${format(value)}${isNow ? " · agora" : ""}`;
      bar.append(tooltip);
      svg.append(bar);
    } else if (isNow) {
      // Sem atividade ainda: um traço na base mantém "agora" visível.
      const tick = Math.max(3, Math.min(6, slot * 0.2));
      svg.append(
        node("rect", {
          class: "bar now-tick",
          x: LEFT + slot * index + (slot - tick) / 2,
          y: TOP + PLOT_HEIGHT - 5,
          width: tick,
          height: 5,
          rx: 2,
        })
      );
    }
    if (ticks.has(index)) svg.append(label(labels[index], LEFT + slot * (index + 0.5), HEIGHT - 8));
  });
}

export function renderLine(
  svg,
  values,
  labels,
  { format = String, unit = "", highlight = -1 } = {}
) {
  const maximum = Math.max(1, ...values);
  grid(svg, maximum, format);
  const slot = (WIDTH - LEFT - RIGHT) / Math.max(1, values.length);
  const ticks = tickIndexes(values.length);

  const points = values
    .map((value, index) => `${LEFT + slot * (index + 0.5)},${TOP + PLOT_HEIGHT - (value / maximum) * PLOT_HEIGHT}`)
    .join(" ");
  svg.append(node("polyline", { class: "line-path", points }));

  if (highlight >= 0 && highlight < values.length) {
    const x = LEFT + slot * (highlight + 0.5);
    svg.append(node("line", { class: "now-line", x1: x, y1: TOP, x2: x, y2: TOP + PLOT_HEIGHT }));
  }

  values.forEach((value, index) => {
    const isNow = index === highlight;
    const x = LEFT + slot * (index + 0.5);
    const y = TOP + PLOT_HEIGHT - (value / maximum) * PLOT_HEIGHT;
    const dot = node("circle", { class: isNow ? "line-point now" : "line-point", cx: x, cy: y, r: 4 });
    const tooltip = node("title");
    tooltip.textContent = `${labels[index]}: ${format(value)}${unit}${isNow ? " · agora" : ""}`;
    dot.append(tooltip);
    svg.append(dot);
    if (ticks.has(index)) svg.append(label(labels[index], x, HEIGHT - 8));
  });
}

/* Mapa de consistência: uma célula por dia, em colunas de semana. */
export function renderHeatmap(host, cells, { today = "" } = {}) {
  host.replaceChildren();
  for (const cell of cells) {
    const square = document.createElement("i");
    square.className = cell.date === today ? "heat now" : "heat";
    square.dataset.level = String(cell.level);
    square.title = cell.tooltip;
    host.append(square);
  }
}

/* Uso por dia da semana: colunas com altura proporcional. */
export function renderWeekdays(host, days, { highlight = "" } = {}) {
  const maximum = Math.max(1, ...days.map((day) => day.count));
  host.replaceChildren();
  for (const day of days) {
    const column = document.createElement("div");
    column.className = day.label === highlight ? "weekday-col now" : "weekday-col";
    const bar = document.createElement("i");
    bar.style.setProperty("--h", `${Math.max(2, (day.count / maximum) * 100)}%`);
    bar.title = `${day.label}: ${day.count} ditado(s) · ${day.words} palavra(s)`;
    const caption = document.createElement("label");
    caption.textContent = day.label;
    column.append(bar, caption);
    host.append(column);
  }
}
