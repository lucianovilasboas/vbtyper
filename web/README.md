# Cliente web

SPA em módulos ES, **sem etapa de build** (nada de Node/npm), servida pelo
próprio backend na mesma origem. Abra <http://127.0.0.1:8765>.

## Como funciona

- `index.html` — estrutura das três telas: **Ditar**, **Histórico** e
  **Atividade**.
- `static/api.js` — cliente fino da API v1 (`fetch` com `credentials:
  same-origin`).
- `static/recorder.js` — envoltório do `MediaRecorder` (WebM/Opus no Chrome,
  Ogg/Opus no Firefox) que devolve um `Blob`.
- `static/app.js` — fluxo: gravar → `POST /transcription-jobs` → acompanhar
  (`GET`) → copiar; além disso, histórico e estatísticas.
- `static/style.css` — tema claro/escuro por `prefers-color-scheme`.
- `static/logo.png` e `static/favicon.png` — a marca, usada no cabeçalho e como
  ícone da aba. São **gerados** por `scripts/build-icons.py` a partir de
  `vb-typer.png`; não edite os PNG à mão.

> Depois de mexer em `index.html` ou nos assets, reinicie o serviço
> (`systemctl --user restart vb-typer-api`): o backend lê a página uma vez, no
> start.

## Autenticação

O backend serve a página em `/` e responde com o token num cookie
**HttpOnly + SameSite=Strict**. O JavaScript nunca vê o token: o navegador o
envia sozinho nas requisições de mesma origem. Um site externo não consegue ler
a resposta nem enviar o cookie (e o backend ainda valida `Host` e `Origin`).

## Fluxo de transcrição

1. O botão grava com `getUserMedia` + `MediaRecorder` e mostra medidor/tempo.
2. Ao parar, o áudio vai como `multipart/form-data` para
   `POST /api/v1/transcription-jobs` (`202` + `job_id`).
3. A interface acompanha `GET /api/v1/transcription-jobs/{id}` até o estado
   terminal; **Cancelar** chama `DELETE`.
4. O texto aparece no campo; **Copiar** usa a área de transferência e registra a
   inserção em `PATCH /api/v1/transcriptions/{id}`.

O backend não digita nada — inserir texto em outros aplicativos é papel dos
clientes desktop.
