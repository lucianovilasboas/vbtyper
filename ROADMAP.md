# ROADMAP — VB Typer 2.0

Pendências combinadas com o Luciano. **Nada aqui está implementado**, exceto o
que estiver marcado como feito.

Última atualização: 18/10/2026 — tudo em `v0.4.1` (backend: 63 testes; desktop:
163 testes).

---

## 1. Modos de transcrição: literal, inteligente e estruturado

**Pedido (Luciano, 18/10):** oferecer três modos de transcrição.

- **Literal:** preserva exatamente as palavras reconhecidas.
- **Inteligente:** converte datas, números, valores e siglas para formatos
  convencionais.
- **Estruturado:** extrai entidades específicas e devolve um JSON conforme um
  esquema definido pelo usuário.

### Literal e Inteligente: **feito em `v0.5.0`**

O padrão continua sendo **literal**; o Inteligente só entra quando o usuário
escolhe (tela de Configurações ou campo `mode` no job). O que foi implementado:

- coluna `mode` no job, no histórico e nas configurações; `raw_text` guarda o
  texto reconhecido, para auditar o ajuste e poder voltar atrás (migração
  `0002_modes`);
- o Inteligente é uma segunda chamada (`/chat/completions`), com a instrução em
  `services/normalize.py`, validada contra a API real: "dezoito de outubro de
  dois mil e vinte e cinco às três e meia da tarde" → **18/10/2025 às 15h30**,
  "cinquenta reais e vinte centavos … trinta por cento" → **R$ 50,20 … 30%**,
  "o c p v … c p f" → **CSV … CPF**;
- **pulo por heurística:** texto sem número/data/valor/sigla não gasta a segunda
  chamada (prosa comum sai com a latência de hoje). A checagem é conservadora:
  um falso "sim" custa latência, um falso "não" custaria o formato pedido;
- **falha do ajuste entrega o literal** (nunca perde o ditado) e registra no log;
- **conexão reaproveitada** no adaptador da OpenAI: antes cada ditado abria um
  cliente HTTP novo, pagando um handshake TLS;
- a dica curta de formatação (`prompt`) só vai na transcrição quando o modo é
  smart — no literal nada enviesa o reconhecimento.

Falta desta parte: mostrar o **texto reconhecido** lado a lado no histórico (hoje
tem um "ver o texto reconhecido") e o mesmo modo no cliente desktop — este já lê
a configuração e envia o modo, então está pronto.

### Estruturado: pendente, e é o que falta decidir

Continua como estava: **não** vai para o cursor (devolve um documento, para a
tela e o histórico), exige **duas etapas** (a transcrição não aceita esquema
JSON) e depende de duas decisões do Luciano:

1. o esquema é **colado como JSON** ou montado por um **construtor de campos**?
2. esquemas nomeados ("despesa", "reunião", "tarefa") para escolher ao ditar?

Fases: colunas de esquema e resultado estruturado → validador que transforma o
esquema do usuário em formato *estrito* aceito pela OpenAI → tela para ver,
copiar e baixar o JSON → exportação.

### Opcionais registrados

- **Cache do ajuste por texto** (tabela pequena com validade): acerta quando se
  repete uma frase; ganho baixo, custo baixo.
- **Cache do resultado da transcrição**: não faz sentido (dois ditados nunca são
  iguais).
- O áudio já é arquivado localmente, o que cobre a outra metade (reenvio).

### O ponto de arquitetura que precisa ficar claro

São **dois tipos de coisa**, não três variantes do mesmo:

| Modo | O que sai | Onde isso vive |
|---|---|---|
| Literal | texto | no cursor (como hoje) |
| Inteligente | texto normalizado | no cursor |
| Estruturado | **JSON** | **não** no cursor — nas telas do app e no histórico |

Não faz sentido inserir JSON no meio de um e-mail. O modo Estruturado devolve um
**documento**: ele pertence à interface (ver, copiar, baixar) e ao histórico, não
ao fluxo de inserção no cursor. Vale confirmar isso com o Luciano.

### O que a API da OpenAI permite

Hoje o backend faz **uma** chamada: `POST /audio/transcriptions` com `model` e
`language` (`backend/src/vb_typer/adapters/openai.py`). Não usa `prompt`, e não
há nenhuma capacidade de chat implementada.

- O endpoint de transcrição **não aceita esquema JSON** (`response_format` só
  tem `text`/`json`/`srt`/`verbose_json`/`vtt`). Logo o modo Estruturado exige
  **duas etapas**: transcrever e depois chamar `/chat/completions` com
  `response_format: json_schema` (Structured Outputs).
- **Inteligente** tem dois caminhos:
  - `prompt` na própria transcrição: **grátis e sem latência extra**, mas é um
    viés de estilo, não garantia;
  - segunda chamada de chat com instruções de normalização: confiável, custa
    ~0,5–2 s de latência e frações de centavo.
- Os dois modos novos, portanto, adicionam **uma segunda chamada** — e latência
  perceptível num ditado por push-to-talk. Decisão do Luciano.

### Onde encaixa no código atual

Pipeline de hoje: `POST /api/v1/transcription-jobs` →
`services/transcription.py::create_job` → `workers/manager.py::_process` chama
`openai.transcribe` → `finish_success(texto)`.

| Peça | Mudança |
|---|---|
| `db/models.py` → `jobs` | coluna `mode` (+ o esquema escolhido) |
| `db/models.py` → `transcriptions` | `mode`, `raw_text` (o cru da ASR) e `structured_json` |
| migração Alembic | nova versão em `db/migrations/versions/` |
| `adapters/openai.py` | nova capacidade de chat (hoje só transcrição e `/models`) |
| API v1 | `mode` no `POST` de jobs; modo padrão em `/api/v1/settings` |
| web | seletor de modo na tela **Ditar**; JSON na tela; selo do modo no Histórico |
| cliente desktop | só literal/inteligente, herdando o padrão de `/settings` (ele **já** lê modelo e idioma a cada ditado) |

**Guardar o texto cru sempre** (`raw_text`) é o que permite auditar, comparar e
desfazer: se o modo inteligente errar um valor, o original continua no histórico.

### Duas decisões de projeto a manter

1. **Falha na segunda chamada nunca perde o ditado.** Se o chat falhar (esquema
   recusado, cota, rede), o job entrega o **texto literal** e registra o motivo.
2. **O esquema do Estruturado é a parte cara.** Structured Outputs exige esquema
   *estrito* (todos os campos obrigatórios, `additionalProperties: false`, tipos
   suportados). O backend precisa **validar e normalizar** o que o usuário
   mandar, senão a chamada quebra.

### Fases propostas

1. **Backend — literal + inteligente.** Coluna `mode`, `raw_text`, migração, a
   segunda chamada e o *fallback*. Testes com `respx` cobrindo os dois modos, a
   falha da segunda chamada e o cancelamento (que precisa valer para as duas
   etapas).
   *Aceite:* ditado literal idêntico ao de hoje; ditado inteligente normaliza
   datas/números; com a API de chat fora do ar, sai o literal e o motivo
   registrado.
2. **Web UI.** Seletor de modo na tela Ditar e selo do modo no Histórico.
3. **Estruturado.** Esquemas **nomeados** (ex.: "despesa", "reunião", "tarefa"),
   validador/normalizador de esquema, o JSON na tela (bonito, copiar, baixar) e
   no histórico, exportação em CSV.
4. **Cliente desktop.** Herdar o modo padrão (literal/inteligente) e reportar no
   `PATCH` de inserção.

### Perguntas em aberto (para o Luciano)

1. **Inteligente:** segunda chamada (confiável, +0,5–2 s) ou começar só com o
   `prompt` grátis? Recomendação: segunda chamada, com o `prompt` junto.
2. **Estruturado:** confirma que **não** vai para o cursor? O esquema é **colado
   como JSON** ou montado por um **construtor de campos** (nome/tipo/descrição)?
3. **Falha na segunda chamada:** entregar o literal (recomendado) ou falhar o job?
4. **Modelo da segunda chamada:** hoje o backend só autoriza modelos de
   transcrição; será preciso uma nova configuração (`gpt-4o-mini`?).

---

## 2. Interface web com a cara do 1.x

**Feito em `v0.4.0`** (commit `a9e6013`). As quatro telas seguem o protótipo do
1.x (`hermes-workspace/vibe-typer/prototype-estatisticas.html`): paleta com o
roxo `#7839e8`, cartões, gráficos em SVG, mapa de consistência das últimas 13
semanas, uso por dia da semana, tabela de histórico com **custo por ditado** e
tela de configurações com miniatura de cada tema (claro/escuro/automático).

O custo por ditado vem da API (`cost_usd` em cada transcrição), calculado pela
tarifa do modelo em `domain/pricing.py` — uma fonte só, sem tabela duplicada no
JavaScript.

### O que falta desta seção

Duas análises que estavam no ROADMAP do 1.x e ainda não existem:

1. **Comparar a semana atual com a anterior**, com variação percentual de
   ditados, palavras e tempo de áudio. Sai quase de graça: são duas chamadas a
   `/stats` com intervalos diferentes (ou um parâmetro novo na API).
2. **Períodos de baixa atividade/pausas**, para acompanhar o padrão de uso — sem
   presumir que o app ativo significa que o usuário está disponível para ditar.

Ideias menores, se valerem: exportar também as estatísticas (hoje só o histórico
tem CSV) e um filtro de modelo na tela de atividade.

---

## 3. Cliente desktop: autostart e empacotamento

**Autostart feito em `v0.4.2`.** O cliente sobe no login por
`vb-typer-desktop.service` (unit de usuário), instalado com
`./scripts/install-desktop-service.sh`, que também grava a entrada no menu de
aplicativos com a marca. A unit declara `DISPLAY`/`XAUTHORITY` porque
`graphical-session.target` não é ativado no Cinnamon, e o cliente trata `SIGTERM`
para desmontar bandeja e indicador ao parar.

### O que falta desta seção

**Empacotamento one-file (PyInstaller)** — para distribuir sem exigir `uv` e o
repositório no disco. Lembrando que **PyGObject não empacota**: a bandeja e o
indicador continuam como helpers rodando no Python do sistema, e o pacote precisa
levar `tray/` e `assets/` (o `tray.resource_base()` já procura em `_MEIPASS`).

---

## 4. macOS e Windows

Pela camada `desktop/src/vb_typer_desktop/platform/`, que já existe e hoje só tem
`linux_x11`. Por sistema:

| Peça | Windows | macOS |
|---|---|---|
| Inserção | `SendInput` com `KEYEVENTF_UNICODE` (via `pynput`, que já faz isso) | CGEvent (exige permissão de Acessibilidade) |
| Áudio | `sounddevice` (não há `arecord`) | `sounddevice` |
| Bandeja | `pystray` | `rumps`/`pystray` |
| Notificações | toast nativo | Notification Center |
| Atalho | `pynput` (sem `pynput` no Linux, por causa do XRecord — ver AGENTS.md) | `pynput` |

Avisos: no Windows a tecla "Super" é a tecla Windows (risco de menu Iniciar /
`Win+L` — atalho configurável por SO); janelas elevadas não aceitam injeção
(UIPI); a paridade só se prova numa máquina Windows/macOS.

---

## 5. Pendências pequenas

- **Ditados gravados pelo navegador ficam com `duration_s = 0`**, e isso agora
  aparece na contabilidade: no histórico essas linhas mostram **custo US$ 0,0000**
  porque o custo é calculado pela duração. O 2.x não extrai duração de WebM/OGG
  (só de WAV, que é o que o cliente desktop manda). Caminho mais curto: o próprio
  navegador **sabe** a duração (tem o cronômetro) — mandar como campo do
  formulário no `POST` e o backend usar esse valor. São ~10 linhas.
- **3 linhas de teste no histórico** (ids 98, 99 e 100 — das minhas verificações
  do indicador, incluindo uma chamada real à OpenAI): **ficam**, por decisão do
  Luciano. Não apagar.
- Retorno do indicador recalibrado em `v0.4.1` (passou de exponencial para
  linear). Se ainda parecer lento no uso, `speed` no `desktop.json` — nada de
  código.
