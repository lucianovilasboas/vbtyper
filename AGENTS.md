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

Antes de encerrar qualquer tarefa: `ruff check`, `ruff format --check` e
`pytest` têm de passar.

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

## Estado atual

- Backend v1 completo (jobs, histórico, estatísticas, configurações, CSV,
  importador do 1.x) — 60 testes.
- Cliente web (Ditar / Histórico / Atividade) servido na mesma origem.
- Próximo: clientes desktop. Antes de escolher a stack, alinhar com o usuário
  (Python/Tk reaproveitando X11 vs. Tauri/Electron multiplataforma).
