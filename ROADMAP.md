# ROADMAP — VB Typer 2.0

Pendências combinadas com o Luciano. **Nada aqui está implementado**, exceto o
que estiver marcado como feito.

Última atualização: 18/10/2026 — backend e cliente desktop em `v0.3.2`
(backend: 61 testes; desktop: 155 testes).

---

## 1. Modos de transcrição: literal, inteligente e estruturado

**Pedido (Luciano, 18/10):** oferecer três modos de transcrição.

- **Literal:** preserva exatamente as palavras reconhecidas.
- **Inteligente:** converte datas, números, valores e siglas para formatos
  convencionais.
- **Estruturado:** extrai entidades específicas e devolve um JSON conforme um
  esquema definido pelo usuário.

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

**Pedido (Luciano, 18/10):** o histórico e a tela de atividades devem ficar mais
parecidos com a versão 1. Não é urgente.

O que já existe para reaproveitar:

- `hermes-workspace/vibe-typer/prototype-estatisticas.html` — protótipo web da
  tela de estatísticas (24 KB);
- a paleta do Tk no 1.x (`LIGHT_COLORS`/`DARK_COLORS`), com tema
  auto/claro/escuro persistido e o roxo `#7839e8` como cor de destaque.

Diagnóstico: a SPA do 2.x **já tem** as métricas (7/30/90 dias, 6 meses, 1 ano,
ritmo, pico, p95, falhas). O que falta é **pele**: tema claro/escuro persistido,
paleta, tipografia, formato da tabela do histórico e visual do gráfico.

Observação: a cor de destaque da SPA é **indigo** (`--brand: #4f46e5`) enquanto a
marca é **violeta**. Alinhar o `--brand` ao violeta da marca é uma linha e faz
parte deste item.

Restrição que vale: **sem build/Node** — ES modules e CSS puro, como hoje.

---

## 3. Cliente desktop: autostart e empacotamento

**Hoje** o cliente roda por `uv run` num processo desanexado: **não sobe no
login** e não reinicia em falha.

- Unit systemd de usuário para o cliente, nos moldes da do backend
  (`deploy/systemd/vb-typer-api.service` + `scripts/install-service.sh`);
- entrada no menu de aplicativos (`.desktop`);
- empacotamento one-file (PyInstaller), lembrando que **PyGObject não empacota**:
  a bandeja e o indicador continuam como helpers no Python do sistema.

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

- **3 linhas de teste no histórico** (ids 98, 99 e 100 — das minhas verificações
  do indicador, incluindo uma chamada real à OpenAI). O Luciano ainda não disse
  se quer que eu apague.
- Confirmar visualmente, num ditado real e mais longo, se a calibração nova do
  indicador (`speed`/`sensitivity` = 1.0) é o ponto de equilíbrio.
