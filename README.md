# VB Typer 2.0 — backend desacoplado

Backend de transcrição de voz com **API REST local**, desacoplado de qualquer
interface. Os clientes (web, desktop Linux/macOS/Windows, scripts) consomem a
mesma API; a regra de negócio, o histórico, os áudios e a credencial da OpenAI
vivem **apenas aqui**.

> Este repositório é a evolução 2.0. O app 1.x em `hermes-workspace/vibe-typer`
> continua intacto e em uso durante a transição.

## Por que desacoplar

Hoje o VB Typer 1.x mistura GUI Tk, captura X11, digitação XTEST, histórico
SQLite e chamada à OpenAI em um único executável Linux. O backend separa isso:

- **Backend (aqui):** recebe áudio, transcreve, persiste, calcula estatísticas.
  Não captura áudio, não digita, não conhece X11/Tk → roda igual em Linux,
  macOS e Windows.
- **Clientes:** cuidam só do que é local a cada plataforma (microfone, atalho,
  inserção de texto, bandeja) e falam com a API.

## Requisitos

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/)
- Cofre do sistema para a chave OpenAI (GNOME Keyring/KWallet no Linux,
  Keychain no macOS, Credential Locker no Windows)
- Conta OpenAI com faturamento habilitado

## Começando

```bash
cd backend
uv sync --extra dev          # cria .venv e instala as dependências
uv run vb-typer-api --setup  # salva a chave OpenAI no cofre (entrada mascarada)
uv run vb-typer-api          # sobe a API em http://127.0.0.1:8765
```

Documentação interativa (OpenAPI): <http://127.0.0.1:8765/docs>

### Autenticação

Toda rota de dados exige um token Bearer. Ele é gerado na primeira execução em
`<config_dir>/api-token` (modo `0600`):

```bash
uv run vb-typer-api --status       # caminhos e se há chave configurada
uv run vb-typer-api --print-token  # imprime o token (sensível)

curl -H "Authorization: Bearer $(uv run vb-typer-api --print-token)" \
     http://127.0.0.1:8765/api/v1/settings
```

A API só aceita `Host` local (`127.0.0.1`, `localhost`, `::1`) e valida o
cabeçalho `Origin`, o que bloqueia requisições vindas de páginas externas
(CSRF/DNS-rebinding). **Nunca** escute em `0.0.0.0`.

### Transcrever

Recomenda-se o fluxo de *tarefa* (assíncrono, cancelável):

```bash
# 1) envia o áudio -> 202 + job_id
curl -sS -H "Authorization: Bearer $TOKEN" \
     -F "file=@gravacao.wav" -F "model=gpt-4o-mini-transcribe" -F "language=pt" \
     http://127.0.0.1:8765/api/v1/transcription-jobs

# 2) acompanha o estado/resultado
curl -sS -H "Authorization: Bearer $TOKEN" \
     http://127.0.0.1:8765/api/v1/transcription-jobs/<job_id>

# 3) cancela (o cliente não insere texto tardio; cobrança já enviada não é desfeita)
curl -sS -X DELETE -H "Authorization: Bearer $TOKEN" \
     http://127.0.0.1:8765/api/v1/transcription-jobs/<job_id>
```

Depois de inserir o texto no aplicativo de destino, o cliente informa o
resultado da inserção (o backend não digita):

```bash
curl -sS -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"inserted": true, "insert_ms": 240}' \
     http://127.0.0.1:8765/api/v1/transcriptions/<id>
```

### Rotas principais

| Método | Rota | Descrição |
| --- | --- | --- |
| GET | `/api/v1/health` | vivacidade (público) |
| GET | `/api/v1/ready` | banco + estado da credencial (público) |
| GET/PATCH | `/api/v1/settings` | modelo, idioma, início da semana |
| POST | `/api/v1/settings/test` | GET de leitura em `/models` da OpenAI |
| POST/GET | `/api/v1/transcription-jobs` | cria (202 + `job_id`) / lista |
| GET/DELETE | `/api/v1/transcription-jobs/{id}` | estado+resultado / cancela |
| GET | `/api/v1/transcriptions` | histórico paginado e filtrável |
| GET/PATCH/DELETE | `/api/v1/transcriptions/{id}` | detalhe / inserção / remoção |
| GET | `/api/v1/transcriptions/export.csv` | exportação (UTF-8 BOM, `;`) |
| GET | `/api/v1/stats` | resumo, série e indicadores |

Detalhes de parâmetros, erros e exemplos: [`docs/api.md`](docs/api.md).

## Interface web

O backend serve a interface web em <http://127.0.0.1:8765> — mesma origem, sem
etapa de build (módulos ES puros). Telas: **Ditar** (gravação pelo navegador,
modelo/idioma, transcrição e cópia), **Histórico** (busca, cópia, exclusão,
CSV) e **Atividade** (períodos de 7/30/90 dias, 6 meses e 1 ano; métricas e
gráfico).

Autenticação do navegador: a página é servida com o token num cookie
**HttpOnly + SameSite=Strict**. O JavaScript nunca vê o token; o backend ainda
valida `Host` e `Origin`. Requisições programáticas continuam usando
`Authorization: Bearer`.

## Importar o histórico do app 1.x

A importação é **somente-leitura** sobre o banco antigo e **idempotente**:

```bash
cd backend
uv run vb-typer-import --source ~/.local/share/vb-typer/history.db
uv run vb-typer-import --source ~/.local/share/vb-typer/history.db --dry-run
```

Cada linha importada guarda `legacy_source`/`legacy_id`, então repetir a
importação não duplica nada. O banco da versão 1.x nunca é alterado.

## Onde ficam os dados

Resolvidos por `platformdirs` (podem ser sobrescritos por `VB_TYPER_DATA_DIR`,
`VB_TYPER_CONFIG_DIR`, `VB_TYPER_DATABASE_PATH`).

| | Linux | macOS | Windows |
| --- | --- | --- | --- |
| dados | `~/.local/share/vb-typer` | `~/Library/Application Support/vb-typer` | `%LOCALAPPDATA%\vb-typer` |
| config | `~/.config/vb-typer` | `~/Library/Preferences/vb-typer` | `%LOCALAPPDATA%\vb-typer` |

O banco é `vb-typer.db` (nome próprio para **não** colidir com o `history.db`
do app 1.x). Áudios em `audio/AAAA/MM/`, banco e token sempre com modo `0600`.

## Rodar como serviço (systemd de usuário)

Para o backend ficar no ar independentemente de terminal ou sessão do OpenCode:

```bash
./scripts/install-service.sh
systemctl --user status vb-typer-api
journalctl --user -u vb-typer-api -f
```

O serviço roda `backend/.venv/bin/vb-typer-api` com `WorkingDirectory` no
backend (para achar o `.env`), `DBUS_SESSION_BUS_ADDRESS` explícito (para o
cofre) e `Restart=on-failure`. Sobe no login e é habilitado por padrão.

Se `api_key_configured` aparecer `false` logo após o boot, o cofre ainda não
estava desbloqueado — `systemctl --user restart vb-typer-api` resolve.

Remover:

```bash
systemctl --user disable --now vb-typer-api
rm ~/.config/systemd/user/vb-typer-api.service
systemctl --user daemon-reload
```

Para manter o serviço ativo mesmo sem login gráfico seria preciso
`loginctl enable-linger "$USER"` (requer sudo) — normalmente desnecessário num
desktop.

## Configuração

Variáveis com prefixo `VB_TYPER_` (veja [`backend/.env.example`](backend/.env.example)):
host/porta, diretórios, token, hosts/origens permitidos, base URL e timeout da
OpenAI, limites de upload, modelos aceitos, retenção de áudio, concorrência do
worker. **Nenhum segredo** é lido do `.env`: a chave vive no cofre.

## Testes e qualidade

```bash
cd backend
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

A suíte cobre autenticação (token, `Host`, `Origin`), ciclo de vida dos jobs
(sucesso, falha do provedor, cancelamento, limites e formatos), histórico,
filtros, CSV, estatísticas (hora/dia/semana/mês, intervalos vazios), permissões
dos arquivos e a importação idempotente do app 1.x. A OpenAI é mockada — os
testes não fazem chamadas faturáveis.

O cliente desktop tem suíte própria, também sem rede:

```bash
cd desktop
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
```

## Estrutura

```
backend/
  src/vb_typer/
    api/          # FastAPI: deps, middleware, rotas v1
    core/         # configuração, caminhos, segurança, logging, datas
    db/           # modelos SQLAlchemy + migrações Alembic
    domain/       # enums e erros de domínio
    schemas/      # contratos Pydantic
    repositories/ # acesso SQL
    services/     # transcrição, histórico, estatísticas, configurações
    adapters/     # OpenAI, cofre, armazenamento de áudio
    workers/      # fila e worker de jobs
    cli/          # importador do app 1.x
  tests/
docs/             # arquitetura, API e migração
web/              # cliente web (SPA sem build, servida pelo backend)
desktop/
  src/vb_typer_desktop/
    daemon.py     # atalho → gravação → job → inserção no cursor
    api.py        # cliente REST e leitura do token
    audio.py      # arecord, validação e reparo do WAV
    hotkey.py     # máquina de estados do Ctrl+Super
    control.py    # socket Unix usado pela bandeja
    tray.py       # bandeja GTK3 (processo separado)
    ui.py         # abre a interface no navegador
    platform/     # adaptadores por sistema (hoje só linux_x11)
  tray/ assets/
  tests/
```

## Cliente desktop (Linux/X11)

Segure **Ctrl+Super** para gravar; solte **Ctrl** ou **Super** para transcrever e
inserir. O texto vai direto no ponto do cursor do aplicativo em foco, por XTEST —
não há área de transferência nem colagem. Enquanto grava, um indicador silencioso
com a onda do microfone aparece junto da janela em foco. Detalhes em
[`desktop/README.md`](desktop/README.md).

## Próximas fases

1. Cliente desktop para macOS e Windows, pela camada `platform/` já existente.
2. Empacotamento one-file e autostart do cliente desktop.
3. Análise semântica opcional sobre o histórico (assíncrona, opt-in).
