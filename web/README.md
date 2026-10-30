# Cliente web

SPA em módulos ES, **sem etapa de build** (nada de Node/npm), servida pelo
próprio backend na mesma origem. Abra <http://127.0.0.1:8765>.

## Como funciona

Quatro telas, na mesma página:

- **Ditar** — grava pelo microfone do navegador **ou envia um arquivo de áudio**
  (WAV, MP3, M4A, OGG e WebM, até 25 MB) e mostra o texto para revisar e copiar.
  Os chips do topo mostram com qual modelo, idioma e perfil você está ditando.
- **Atividade** — métricas do período, dois gráficos (volume e ritmo de fala),
  mapa de consistência das últimas 13 semanas e uso por dia da semana.
- **Histórico** — tabela com quando, áudio, palavras, **custo estimado** e o
  texto de cada ditado; busca, exclusão e exportação em CSV.
- **Configurações** — aparência (claro/escuro/automático), modelo, idioma, início
  da semana, perfis de texto (com o **destino do texto**: normal ou terminal/TUI),
  estado da credencial e teste de conexão.

Arquivos:

- `index.html` — a estrutura das quatro telas.
- `static/api.js` — cliente fino da API v1 (`fetch` com `credentials:
  same-origin`).
- `static/recorder.js` — envoltório do `MediaRecorder` (WebM/Opus no Chrome,
  Ogg/Opus no Firefox) que devolve um `Blob`.
- `static/app.js` — fluxo de gravação e envio de arquivo, histórico, atividade e
  configurações.
- `static/charts.js` — gráficos em SVG puro (sem biblioteca): barras, linha,
  mapa de consistência e uso por dia da semana.
- `static/style.css` — a paleta do 1.x (o roxo `#7839e8`) e os componentes. O
  tema é escolhido em `data-theme` no `<html>`, com `auto` seguindo o sistema.
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

O card **Enviar arquivo** entra no mesmo pipeline: escolhe (ou arrasta) o áudio,
mostra nome, tamanho e a duração lida dos metadados do próprio arquivo, e só
envia depois do clique em **Transcrever arquivo**. O resultado cai no mesmo
campo e no histórico, com a duração que o navegador conseguiu ler.

O backend não digita nada — inserir texto em outros aplicativos é papel dos
clientes desktop.

## Introdução da marca

`static/brand-intro.js` e `static/brand-intro.css` mostram o rio original com
ondulações SVG e uma pequena pedra saltando, por **1,8 segundo** (incluindo a
saída). O cabeçalho e todos os PNG/ícones permanecem originais. Não há áudio,
CDN, dependências de runtime ou etapa de build.

- Executa uma vez por documento, tanto no navegador quanto no shell do PWA;
  navegação interna e retorno à janela não repetem a introdução.
- A inicialização da API roda em paralelo; a introdução não indica prontidão.
- Clique/toque, qualquer tecla ou foco em um controle dispensam a apresentação
  sem consumir a interação. Há também **Pular introdução**, sem foco automático.
- `prefers-reduced-motion: reduce` e documentos abertos em segundo plano pulam
  a apresentação. Mudar a preferência durante a animação também a dispensa.
- Sem JS/CSS da introdução, o overlay não aparece; erro no PNG o dispensa.
  O CSS também o oculta em 1,8 s caso a limpeza JS falhe. O conteúdo da aplicação
  nunca recebe `inert`, bloqueio de rolagem ou armadilha de foco.
- O splash nativo de instalação/abertura do sistema continua estático. O worker
  `vb-typer-v2-brand-intro` inclui os novos assets e o ícone maskable existente;
  só remove caches antigos com prefixo `vb-typer-`.

### Prévia isolada (sem reiniciar o aplicativo em uso)

Na raiz do repositório:

```sh
python3 web/tests/serve_preview.py 8877      # http://127.0.0.1:8877
```

É um servidor estático que só existe para a prévia: mapeia `/sw.js` e
`/manifest.webmanifest` para `static/` e responde `503` em `/api/*` de propósito.
Recarregue para repetir a introdução; Ctrl+C encerra. **Não é o backend** — API,
transcrição e instalação PWA não funcionam aí. Para a integração real, o backend
precisa carregar o novo `index.html` no próximo início autorizado; não reinicie o
serviço em uso só para a prévia.

### Verificação automatizada em Chromium

Playwright é uma dependência **apenas de teste**, instalada em venv separado:

```sh
python3 -m venv "$HOME/.cache/vb-intro-test-venv"
"$HOME/.cache/vb-intro-test-venv/bin/pip" install -r web/tests/requirements.txt
"$HOME/.cache/vb-intro-test-venv/bin/python" -m playwright install chromium
VB_INTRO_SCREENSHOTS="$HOME/.cache/vb-intro-screenshots" \
  "$HOME/.cache/vb-intro-test-venv/bin/python" -m unittest discover -s web/tests -v
```

A suíte cria e encerra o mesmo servidor de prévia — em porta efêmera de
`127.0.0.1` — usa perfis isolados e API indisponível de propósito. Cobre término,
dispensa, navegação, movimento reduzido, falhas de assets/JS, fallback CSS, temas,
viewport móvel e ancoragem das ondulações na fita real do `logo.png`; registra um
service worker real, verifica a migração do cache e a abertura offline. As
capturas congelam frames CSS em 470 ms (impacto) e 1250 ms (nome revelado) para
comparação visual. Não simulam uma instalação nativa do PWA no sistema operacional.

