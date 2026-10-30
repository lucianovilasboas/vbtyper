// Testes do cliente da API: uma página de erro HTML (proxy, 502/503) não pode
// virar mensagem de interface. Rodar com: node --test web/tests/
import assert from "node:assert/strict";
import { test } from "node:test";

import { api } from "../static/api.js";

const HTML_ERROR = `<!DOCTYPE HTML>
<html lang="en"><head><title>Error response</title></head>
<body><h1>Error response</h1><p>Error code: 503</p>
<p>Message: Isolated preview: no backend.</p></body></html>`;

function reply(body, { status = 500, type = "text/html" } = {}) {
  globalThis.fetch = async () => new Response(body, { status, headers: { "content-type": type } });
}

async function messageFrom(call) {
  try {
    await call();
  } catch (error) {
    return error;
  }
  assert.fail("a chamada deveria ter falhado");
}

test("página HTML de erro vira mensagem curta, sem tags", async () => {
  reply(HTML_ERROR, { status: 503 });
  const error = await messageFrom(() => api.ready());
  assert.equal(error.message, "Erro HTTP 503");
  assert.equal(error.status, 503);
  assert.ok(!/[<>]/.test(error.message));
});

test("texto puro curto é preservado como mensagem", async () => {
  reply("Manutenção programada", { status: 503, type: "text/plain" });
  const error = await messageFrom(() => api.ready());
  assert.equal(error.message, "Manutenção programada");
});

test("texto puro muito longo não vira mensagem", async () => {
  reply("x".repeat(500), { status: 502, type: "text/plain" });
  const error = await messageFrom(() => api.ready());
  assert.equal(error.message, "Erro HTTP 502");
});

test("JSON do backend mantém a mensagem e o código", async () => {
  reply(
    JSON.stringify({ error: { code: "no_api_key", message: "Chave OpenAI ausente." } }),
    { status: 409, type: "application/json" }
  );
  const error = await messageFrom(() => api.testConnection());
  assert.equal(error.message, "Chave OpenAI ausente.");
  assert.equal(error.code, "no_api_key");
  assert.equal(error.status, 409);
});

test("falha de rede continua com mensagem própria", async () => {
  globalThis.fetch = async () => {
    throw new TypeError("fetch failed");
  };
  const error = await messageFrom(() => api.ready());
  assert.match(error.message, /backend/i);
});
