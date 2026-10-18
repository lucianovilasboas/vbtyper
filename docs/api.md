# API v1

Base: `http://127.0.0.1:8765/api/v1`

Todas as rotas de dados exigem `Authorization: Bearer <token>`. As rotas
públicas (`health`, `ready`) não exigem token. Respostas de erro seguem sempre o
mesmo formato:

```json
{ "error": { "code": "invalid_model", "message": "Modelo inválido. Use um de: ...", "request_id": "…" } }
```

Códigos: `unauthorized` (401), `forbidden` (403), `invalid_host` (400),
`not_found` (404), `validation_error` (422), `invalid_audio` (400),
`audio_too_large` (413), `unsupported_media_type` (415), `invalid_model` (422),
`api_key_missing` (503), `provider_error` (502), `internal_error` (500).

## Saúde

### `GET /health` (público)

```json
{ "status": "ok", "app": "VB Typer API", "version": "0.1.0" }
```

### `GET /ready` (público)

```json
{ "status": "ok", "database": true, "api_key_configured": false, "models": ["gpt-4o-mini-transcribe", "gpt-transcribe"] }
```

## Configurações

### `GET /settings`

```json
{ "model": "gpt-4o-mini-transcribe", "language": "pt", "week_start": "monday",
  "api_key_configured": true, "allowed_models": ["gpt-4o-mini-transcribe", "gpt-transcribe"] }
```

### `PATCH /settings`

```json
{ "model": "gpt-transcribe", "language": "en", "week_start": "sunday" }
```

Todos os campos são opcionais. `model` precisa estar em `allowed_models`
(`invalid_model`); `week_start` é `monday` ou `sunday`.

### `POST /settings/test`

Faz um `GET` somente leitura em `/models` da OpenAI. Não transcreve áudio.

```json
{ "ok": true, "models_available": 42, "message": "Conexão com a OpenAI verificada." }
```

## Jobs de transcrição

### `POST /transcription-jobs` → `202`

`multipart/form-data`:

| Campo | Obrigatório | Descrição |
| --- | --- | --- |
| `file` | sim | áudio (wav, webm, ogg, mp3, m4a); até 25 MB |
| `model` | não | padrão: configuração atual |
| `language` | não | padrão: `pt` |

```json
{ "id": "3f0c…", "status": "queued", "created_at": "2026-10-18T18:44:02",
  "model": "gpt-transcribe", "language": "pt", "size_bytes": 32044,
  "duration_s": 1.0, "result": null }
```

### `GET /transcription-jobs/{id}`

Devolve o mesmo objeto; quando concluído, `result` traz a transcrição.

```json
{ "id": "3f0c…", "status": "succeeded", "duration_s": 1.0,
  "transcription_id": 12, "error": null,
  "result": { "id": 12, "text": "olá mundo", "words": 2, "inserted": false, "…": "…" } }
```

`status`: `queued | running | succeeded | failed | canceled`.

### `GET /transcription-jobs?limit=20&status=succeeded`

Lista os jobs mais recentes.

### `DELETE /transcription-jobs/{id}`

Cancela. Jobs já terminais são devolvidos sem alteração.

## Histórico

### `GET /transcriptions`

| Query | Descrição |
| --- | --- |
| `limit` (1–500), `offset` | paginação (mais recentes primeiro) |
| `from`, `to` | `AAAA-MM-DD` ou ISO-8601 (limite superior fecha o dia) |
| `model` | filtra por modelo |
| `inserted` | `true`/`false` |
| `q` | busca em texto e mensagem de erro |

```json
{ "items": [ { "id": 12, "created_at": "2026-10-18T18:44:02", "text": "olá", "words": 1,
  "duration_s": 1.0, "audio_bytes": 32044, "model": "gpt-transcribe", "language": "pt",
  "transcribe_ms": 1200, "insert_ms": 240, "inserted": true, "error": null } ],
  "total": 1, "limit": 20, "offset": 0 }
```

### `GET /transcriptions/{id}`

Item isolado (`404` se não existir).

### `PATCH /transcriptions/{id}`

```json
{ "inserted": true, "insert_ms": 240 }
```

### `DELETE /transcriptions/{id}` → `204`

Remove o registro **e** o áudio associado.

### `GET /transcriptions/export.csv`

Exporta o histórico filtrado com as mesmas queries da listagem. O arquivo usa
UTF-8 com BOM e separador `;`, abrindo direto no Excel pt-BR.

## Estatísticas

### `GET /stats?granularity=day&from=2026-09-19&to=2026-10-18`

`granularity`: `hour | day | week | month` (padrão `day`). Sem `from`/`to`, usa
os últimos 30 dias.

```json
{
  "from": "2026-09-19 00:00:00",
  "to": "2026-10-18 23:59:59",
  "granularity": "day",
  "summary": { "total": 12, "seconds": 540.0, "bytes": 17280000, "chars": 4200,
    "words": 780, "failures": 1, "not_inserted": 2, "avg_ms": 1250.0,
    "first_at": "2026-09-20 08:00:00", "last_at": "2026-10-18 18:44:02", "cost_usd": 0.027 },
  "series": [ { "bucket": "2026-10-18", "label": "18/10", "count": 1, "seconds": 60.0, "words": 120 } ],
  "insights": { "words_per_minute": 86.6, "dictations_per_active_day": 1.5,
    "average_duration": 45.0, "peak_hour": "09:00", "peak_hour_count": 4,
    "api_average_ms": 1250.0, "api_p95_ms": 2100,
    "longest": { "text": "…", "duration_s": 120.0, "words": 300 }, "failure_rate": 0.083 }
}
```

A série sempre inclui períodos sem uso (gráfico contínuo). Semanas começam
conforme `week_start`. Intervalos grandes demais para `hour` retornam
`range_too_large`.
