# Arquitetura

## Visão geral

```
clientes (web, desktop, scripts)
        │  HTTP + Bearer token (loopback)
        ▼
   API v1 (FastAPI)  ──  middleware: Host/Origin, request-id, CORS
        │
        ▼
   serviços de aplicação  (transcrição, histórico, estatísticas, configurações)
        │
        ├── repositórios  ──►  SQLite (SQLAlchemy + Alembic)
        ├── adaptador OpenAI
        ├── adaptador de cofre (keyring)
        └── armazenamento de áudio (filesystem)
```

Regra de ouro: **nenhum front-end** importa módulos de negócio, fala com a
OpenAI ou abre o banco. O backend é o único proprietário do histórico, dos
áudios e da credencial.

## Camadas

| Pacote | Responsabilidade |
| --- | --- |
| `core/` | configuração (`pydantic-settings`), caminhos (`platformdirs`), segurança (token, Host/Origin), logging, datas |
| `db/` | modelos SQLAlchemy 2 e migrações Alembic |
| `domain/` | enums e erros esperados, com o código HTTP associado |
| `schemas/` | contratos de entrada/saída (Pydantic v2) |
| `repositories/` | consultas SQL isoladas |
| `services/` | regras de negócio síncronas |
| `adapters/` | integrações externas (OpenAI, cofre, disco) |
| `workers/` | fila e worker assíncrono dos jobs |
| `api/` | rotas, dependências e middleware |

As dependências apontam sempre para dentro (`api → services → repositories →
db`), nunca o contrário.

## Ciclo de vida de um job

1. `POST /api/v1/transcription-jobs` valida modelo/idioma, grava o áudio em
   `audio/AAAA/MM/` e cria a linha do job com `status=queued` (resposta `202`).
2. O job entra numa `asyncio.Queue`; um dos workers chama `claim`, que o marca
   `running` (ou `canceled`, se o cancelamento chegou antes).
3. O worker lê o áudio, obtém a chave no cofre e chama a OpenAI.
4. Sucesso → cria a linha em `transcriptions` e marca o job `succeeded`,
   referenciando `transcription_id`.
5. Falha → marca `failed` com a mensagem; registra histórico quando a duração é
   conhecida (paridade com o app 1.x).
6. Cancelamento → `DELETE` marca `cancel_requested`, cancela a tarefa e leva o
   job a `canceled`, apagando o áudio.

Estados: `queued → running → {succeeded, failed, canceled}`.

### Cancelamento

Cancelar interrompe **o aguardo e a inserção no cliente**, mas **não desfaz
cobrança** de uma requisição já entregue à OpenAI. Esse é o mesmo compromisso do
app 1.x e está refletido no código e nos testes.

### Reinício da API

Ao subir, jobs `running` são marcados `failed` (“Interrompido pelo encerramento
da API.”) e jobs `queued` são re-enfileirados, pois o áudio ainda está no disco.

## Estado de inserção

O backend não digita texto. A API devolve a transcrição; o cliente insere no
aplicativo de destino e depois informa o resultado:

```
PATCH /api/v1/transcriptions/{id}
{ "inserted": true, "insert_ms": 240 }
```

Assim `inserted`/`insert_ms` continuam refletindo a realidade sem que o backend
dependa de X11.

## Modelo de segurança

- Escuta apenas `127.0.0.1` por padrão.
- Token Bearer em arquivo `0600`, gerado na primeira execução, comparado com
  `secrets.compare_digest`.
- `Host` restrito ao loopback; `Origin` validado contra uma allowlist
  (`http://127.0.0.1:<porta>`, `http://localhost:<porta>` e
  `VB_TYPER_CORS_ORIGINS`). Requisições sem `Origin` (clientes nativos) passam.
- A chave da OpenAI nunca é exposta: as rotas só informam
  `api_key_configured`. Gravação da chave só pelo fluxo nativo/CLI
  (`vb-typer-api --setup`).
- Logs não registram áudio, texto transcrito, tokens nem chaves.

## Decisões

- **SQLite + SQLAlchemy + Alembic:** um único arquivo, zero servidor, com
  migrações versionadas — adequado a um app local e multiplataforma.
- **Fluxo de job (assíncrono):** preserva cancelamento e estados de
  processamento e atende vários consumidores; um `POST` síncrono perderia isso.
- **Horário local no banco (`YYYY-MM-DD HH:MM:SS`):** faz os baldes de
  hora/dia/semana refletirem o fuso do usuário sem conversões frágeis.
- **`platformdirs`:** diretórios corretos em cada sistema; no Linux coincidem
  com o app 1.x, mas o banco tem nome próprio (`vb-typer.db`) para nunca
  colidir com `history.db`.
