// Service worker do VB Typer.
//
// Existe por dois motivos: sem ele o navegador não oferece a instalação do PWA,
// e ele deixa o app abrir mesmo sem rede. A estratégia é **rede primeiro** — o
// cache é só a reserva para quando não há conexão, então uma versão nova nunca
// fica presa atrás de um cache velho.
//
// `/api/*` nunca é interceptado: dados e credenciais não vão para o cache.

const CACHE = "vb-typer-v2-brand-intro";

const SHELL = [
  "/",
  "/manifest.webmanifest",
  "/static/app.js",
  "/static/api.js",
  "/static/charts.js",
  "/static/recorder.js",
  "/static/wave.js",
  "/static/style.css",
  "/static/brand-intro.js",
  "/static/brand-intro.css",
  "/static/logo.png",
  "/static/favicon.png",
  "/static/icon-192.png",
  "/static/icon-512.png",
  "/static/icon-maskable-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys
        .filter((key) => key.startsWith("vb-typer-") && key !== CACHE)
        .map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname === "/sw.js") return;

  const cacheable =
    url.pathname === "/" ||
    url.pathname === "/manifest.webmanifest" ||
    url.pathname.startsWith("/static/");

  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response.ok && cacheable) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(request, copy));
        }
        return response;
      })
      .catch(() => caches.match(request).then((hit) => hit || caches.match("/")))
  );
});
