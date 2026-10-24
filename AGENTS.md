# AGENTS.md — VB Typer 2.0

Instruções para agentes que trabalharem neste repositório. Leia antes de editar.

## Regra inviolável

**Nunca altere `/home/luciano/hermes-workspace/vibe-typer`.** Aquele é o app 1.x,
em uso diário e em produção. Este repositório (2.0) é a evolução e não pode
quebrar, mover nem "melhorar" o 1.x. Leitura para consulta é permitida;
escrita, não.

## O que é este projeto

Backend de transcrição de voz com API REST local, desacoplado de interface, mais
um cliente web servido pelo próprio backend. Os clientes desktop
(Linux/macOS/Windows) virão depois e consumirão a mesma API.

O backend é o único dono do histórico, dos áudios e da credencial OpenAI. Ele
**não** captura áudio, não digita texto e não conhece X11/Tk — é isso que o
mantém multiplataforma.

## Stack

Python 3.11+ (ambiente gerenciado por `uv`), FastAPI + Pydantic v2 + uvicorn,
SQLAlchemy 2 + Alembic (SQLite), httpx, keyring, platformdirs, pytest + respx +
asgi-lifespan, ruff. Cliente web em módulos ES puros, **sem build/Node**.

## Comandos

```bash
cd backend
uv sync --extra dev
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run vb-typer-api                # sobe em http://127.0.0.1:8765
uv run vb-typer-api --setup        # salva a chave OpenAI no cofre
uv run vb-typer-api --status
uv run vb-typer-api --print-token  # token Bearer (sensível)
uv run vb-typer-import --source ~/.local/share/vb-typer/history.db
```

O cliente desktop é um projeto `uv` próprio, para o backend não herdar
dependências de plataforma:

```bash
cd desktop
uv sync --extra dev
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run vb-typer-desktop            # ditado por Ctrl+Super, com bandeja
uv run vb-typer-desktop --status   # API, token e preferências
uv run vb-typer-desktop --self-test
uv run vb-typer-desktop --notices balloons   # avisos como antes (balões)
../scripts/install-desktop-service.sh        # habilita no login (systemd)
```

Antes de encerrar qualquer tarefa: `ruff check`, `ruff format --check` e
`pytest` têm de passar **nos dois projetos** (backend e desktop).

## Convenções

- Identificadores (variáveis, funções, classes, módulos) em **inglês**;
  docstrings, mensagens de erro e documentação em **pt-BR** — igual ao app 1.x.
- Linha máxima de 100 caracteres; formatação e imports pelo `ruff`.
- Tipos modernos: `from __future__ import annotations`, `X | None`.
- Sem dependência nova sem necessidade real (o backend será empacotado
  futuramente; cada dependência pesa).
- Não use `Base.metadata.create_all`: o esquema é versionado por migrações
  Alembic em `backend/src/vb_typer/db/migrations/`.

## Invariantes de arquitetura

1. Dependências apontam para dentro: `api → services → repositories → db`.
   Nada de SQL nas rotas nem lógica de negócio em `main.py`.
2. Rotas são finas: validam contrato, chamam serviço, devolvem esquema.
3. Segredos: a chave OpenAI só é lida pelo `SecretsAdapter`; nenhuma rota a
   expõe (apenas `api_key_configured`). Nunca logue áudio, texto transcrito,
   token ou chave.
4. Rede: escuta só em `127.0.0.1`. `Host` e `Origin` são validados. O app web
   usa cookie `HttpOnly` + `SameSite=Strict`; clientes programáticos usam
   `Authorization: Bearer`. Nada de `0.0.0.0` sem autorização explícita.
5. Transcrição é assíncrona (job): `POST` devolve `202 + id`, o worker processa,
   `DELETE` cancela. Cancelar interrompe o aguardo/inserção, **não** estorna
   cobrança já enviada à OpenAI — isso é intencional e documentado.
6. O backend não digita texto. O cliente reporta a inserção via
   `PATCH /api/v1/transcriptions/{id}` com `{inserted, insert_ms}`.
7. Datas no banco são horário **local** em `YYYY-MM-DD HH:MM:SS` (string), para
   os baldes de hora/dia/semana refletirem o fuso do usuário.
8. O banco chama-se `vb-typer.db` e **nunca** `history.db` (que pertence ao
   1.x). Áudios em `audio/AAAA/MM/`; banco e token com modo `0600`.
9. Estatísticas filtram o intervalo no SQL e geram baldes contínuos (inclusive
   vazios) em Python; semanas respeitam `week_start`.
10. Erros de domínio estendem `DomainError` (com `status_code` e `code`) e são
    convertidos no handler global para `{"error": {code, message, request_id}}`.
11. O cliente desktop insere texto **direto no ponto do cursor** (XTEST no Linux).
    É proibido colar, usar área de transferência ou ativar janela — há um teste de
    invariante (`desktop/tests/test_source_invariants.py`) que varre o código-fonte
    e falha se qualquer um desses aparecer.
12. O cliente desktop usa socket de controle próprio
    (`vb-typer-desktop-<uid>.sock`), distinto do `vb-typer-<uid>.sock` do 1.x: os
    dois rodam em paralelo e não podem se confundir nem disputar o arquivo.
13. O cliente desktop não conhece o cofre nem a chave: fala só com a API pelo
    token em `~/.config/vb-typer/api-token`. Nada de SQLite, nada de OpenAI direta.
14. Os avisos do ditado são do **cliente**, não do backend: preferências em
    `~/.config/vb-typer/desktop.json`. O padrão é o indicador visual silencioso;
    balões do sistema só para erro. `--notices balloons` restaura o
    comportamento antigo, sem mexer em código.
15. O indicador e a bandeja são helpers GTK3 em **processo separado**, no Python
    do sistema (`/usr/bin/python3`) — o PyGObject não empacota no PyInstaller.
    Eles só leem o estado pelo socket de controle; nenhuma lógica do ditado mora
    ali. `tray/tray_helper.py` veio do 1.x e mantém a estrutura original; as
    adições do 2.0 estão marcadas no arquivo (o item **Perfis** e o submenu dele),
    com o resto intocado. **Não use `RadioMenuItem`/`CheckMenuItem` nesse menu:**
    o host do AppIndicator constrói o menu no primeiro uso e ativava um item
    sozinho, trocando a escolha sem clique. Os itens de perfil são simples, com o
    vigente marcado no próprio rótulo, e o submenu é reconstruído quando a lista
    muda (o item some quando não há perfis).
16. O perfil de texto é `literal` ("Transcrição fiel") por **padrão**; os demais
    perfis passam pela segunda chamada (modo smart). A escolha mora em
    `app_settings.default_profile` — o cliente desktop envia **`profile`** no job
    (nunca `mode`) e a bandeja grava `default_profile`, o mesmo lugar em que a
    interface edita. O texto reconhecido é guardado em `transcriptions.raw_text`
    e o ajuste **nunca** derruba o ditado: falhou, entrega o literal. Textos sem
    nada a converter (prosa comum) pulam a segunda chamada — a heurística está em
    `services/normalize.py` e é conservadora de propósito.
17. Ícones e marca são **gerados** por `scripts/build-icons.py` a partir de
    `vb-typer.png` (raiz do repositório):
    `desktop/assets/tray_*.png` (bandeja, uma cor por estado) e
    `web/static/logo.png` + `favicon.png` (telas do app). Não edite esses PNG à
    mão — rode o gerador. Depois de mexer em `web/`, reinicie o serviço: o
    backend lê `index.html` uma vez, no start.

18. A troca de perfil por atalho é **temporária**: o daemon guarda o perfil do
    próximo ditado em memória (`profile_override`) e só a bandeja ou a interface
    mudam o `default_profile` do backend. As combinações vêm das configurações do
    backend (`app_settings.hotkeys`), são editáveis em **Configurações › Atalhos** e
    o cliente as aplica em até 10 s, sem reiniciar. No Linux elas são **capturadas**
    com `XGrabKey` (o aplicativo não as vê; sem o grab, `Ctrl+Alt+Tab` trocaria de
    aba); o atalho de gravar (Ctrl+Super) continua só observado, sem grab. A
    gramática é validada no backend (`domain/hotkeys.py`) e recusa Ctrl+Super juntos.
19. Os perfis de texto vivem todos no banco (`profiles`). Os dez padrões são
    semeados **uma única vez** na primeira inicialização
    (`app_settings.profiles_seeded`) a partir de `domain/profiles.py`; depois são
    editáveis e removíveis, e apagar um não o ressuscita. A transcrição fiel
    (`literal`) é a base do ditado e o fallback do `default_profile`: pode ser
    renomeada, mas **não** excluída. `profiles.seeded` marca a origem (badge
    "padrão") e `sort_order` preserva a ordem curada; personalizados vêm por nome.

## Testes

- Use o cliente ASGI (`httpx.ASGITransport` + `LifespanManager`), nunca o
  `TestClient` do Starlette.
- **Nunca** faça chamadas reais à OpenAI: use `respx_mock`. Testes não podem
  gerar cobrança.
- Isole o cofre: a fixture autouse `isolate_keyring` impede acesso ao keyring
  real. Para simular chave configurada, use a fixture `with_api_key` (env).
- Use `tmp_path` para diretórios; jamais escreva em dados reais do usuário.
- Cubra caminho feliz **e** falha: áudio vazio/excedente/formato inválido, chave
  ausente, erro HTTP do provedor, cancelamento sem transcrição tardia, token e
  origem inválidos.

No cliente desktop valem as mesmas regras, mais: use os dublês de
`desktop/tests/fakes.py` (plataforma, API e gravador) — nenhum teste abre
microfone, conexão X ou rede. A inserção real só se verifica à mão, numa sessão
X11 com uma janela de texto em foco.

## Git

- Branch `main`; commits no padrão Conventional Commits
  (`feat(api): ...`, `fix(web): ...`, `test: ...`, `docs: ...`).
- Commits pequenos e coesos; mensagens em português são aceitas, o prefixo é em
  inglês.
- Sem remote configurado ainda. Tags de versão: `v0.1.0`, `v0.2.0`, ...

## Serviço (systemd de usuário)

```bash
./scripts/install-service.sh
systemctl --user status vb-typer-api
journalctl --user -u vb-typer-api -f
systemctl --user restart vb-typer-api
systemctl --user disable --now vb-typer-api   # + rm ~/.config/systemd/user/vb-typer-api.service
```

A unit roda `backend/.venv/bin/vb-typer-api` com `WorkingDirectory` no backend
(para achar o `.env`) e `DBUS_SESSION_BUS_ADDRESS` explícito (para o keyring).
Se `api_key_configured` vier `false` logo após o login, o cofre ainda não estava
desbloqueado: `systemctl --user restart vb-typer-api` resolve.

O cliente desktop tem a unit própria (`vb-typer-desktop.service`), instalada por
`./scripts/install-desktop-service.sh`, que também cria a entrada no menu. Ela
declara `DISPLAY` e `XAUTHORITY` porque `graphical-session.target` **não** é
ativado no Cinnamon (por isso o alvo é `default.target`, como no backend) e o
cliente falha sem sessão gráfica — daí `Restart=on-failure` com `RestartSec=3`,
que resolve sozinho se o serviço subir antes do X. O cliente trata `SIGTERM`,
então parar ou reiniciar o serviço desmonta bandeja e indicador junto.

## Estado atual

O backlog combinado com o usuário vive em [`ROADMAP.md`](ROADMAP.md) — leia antes
de propor trabalho novo.

- Backend v1 completo (jobs, histórico, estatísticas, configurações, CSV,
  importador do 1.x) — 60 testes.
- Cliente web (Ditar / Histórico / Atividade) servido na mesma origem.
- Cliente desktop Linux/X11 completo (atalho, gravação, job, inserção no cursor,
  bandeja, indicador visual, interface no navegador) — 146 testes. Verificado à
  mão: XTEST com acentos, ciclo de vida do daemon, ditado ponta a ponta e as
  quatro fases do indicador (foto por fase, com API simulada).
- Próximo: macOS e Windows pela camada `desktop/src/vb_typer_desktop/platform/`
  (adaptadores de áudio, inserção e bandeja), depois empacotamento one-file.

### Decisões já fechadas do cliente desktop

- Stack Python com `httpx` para a API; sem Tk — a interface é a SPA no navegador
  (modo app quando houver Chromium, senão janela nova no Firefox).
- **Sem `pynput` no Linux**: o listener de XRecord não encerra de forma confiável
  (`stop()` retorna, a thread continua viva e cada pausa deixaria contexto X
  pendurado). O atalho é observado consultando `XQueryKeymap` a cada 25 ms.
- `arecord` leva ~300 ms para abrir o dispositivo: os primeiros instantes de uma
  gravação muito curta podem faltar (mesmo comportamento do 1.x).
- Avisos: indicador visual silencioso por padrão (sem balão, sem som), ancorado
  na base da janela em foco; balões ficam para erro. A volta é
  `--notices balloons`.
- A fase de gravação do indicador é a **mesma onda da tela Ditar**: linha
  colorida com o gradiente do canvas web, desenhada a partir das amostras reais
  do microfone; sem amostras ainda, um envelope senoidal de repouso. A fase de
  transcrição é um **anel fino girando** na borda do painel, com uma frase
  minúscula por cima (“Transcrevendo…” ou “Aplicando perfil…”, conforme
  `jobs.phase`), não uma barra que desliza — assim as duas fases nunca se
  confundem. `"shape": "bar"` no `desktop.json` troca a gravação por uma barra de
  nível ancorada à esquerda.
- A onda do indicador usa **áudio real**: o daemon lê a cauda do WAV em andamento
  (`Recorder.waveform`, 512 quadros) e envia 256 pontos no snapshot apenas quando
  está gravando, o indicador está ligado e o `shape` é `wave`. Como o `arecord`
  não tem o AGC do navegador, o helper aplica **ganho automático** (pico alvo
  ~60%, no máximo 5×, ataque rápido e liberação lenta, sem amplificar silêncio);
  `sensitivity` multiplica onda e barra. O nível do medidor do `arecord` continua
  alimentando a barra opcional, e a captura usa `--period-size=256` (~17 ms por
  nível, contra ~140 ms do padrão). Para a barra, o ataque é por constante de
  tempo (~35 ms) e o **retorno é linear** (350%/s, zerando abaixo de 4%):
  exponencial no retorno deixa uma cauda que se percebe como lentidão. O estado é
  consultado a cada 30 ms e o desenho roda a ~50 fps.
