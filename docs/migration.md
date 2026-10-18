# Migração do VB Typer 1.x

O backend 2.0 **não altera** o app 1.x. Os dois podem conviver: o backend usa
`vb-typer.db`, o app 1.x usa `history.db`, ambos sob `~/.local/share/vb-typer`
(no Linux).

## Importar o histórico

```bash
cd backend
uv run vb-typer-import --source ~/.local/share/vb-typer/history.db
```

Opções:

| Opção | Descrição |
| --- | --- |
| `--source` | `history.db` do 1.x **ou** o diretório que o contém |
| `--audio-dir` | diretório de áudios do 1.x, se os caminhos gravados não existirem mais |
| `--database` | banco de destino (padrão: o do backend) |
| `--dry-run` | apenas conta o que seria importado, sem gravar |

O banco de origem é aberto em modo somente-leitura
(`file:…?mode=ro`). Os testes verificam que o arquivo permanece byte a byte
idêntico após a importação.

## Idempotência

Cada linha importada guarda:

- `legacy_source` — caminho absoluto do banco de origem;
- `legacy_id` — o `id` original.

Existe uma restrição única sobre `(legacy_source, legacy_id)`, então rodar a
importação novamente **não duplica** nada: as linhas já presentes são contadas
como “ignoradas”.

## Mapeamento de colunas

| 1.x (`history.db`) | 2.0 (`vb-typer.db`) |
| --- | --- |
| `id` | `legacy_id` (+ `legacy_source`) |
| `created_at` | `created_at` (mesmo formato `AAAA-MM-DD HH:MM:SS`, horário local) |
| `text`, `words`, `duration_s`, `audio_bytes` | iguais |
| `model`, `language` | iguais |
| `transcribe_ms`, `insert_ms`, `inserted`, `error` | iguais |
| `audio_path` | copiado para `audio/AAAA/MM/` e apontado no novo registro |

Se o 1.x não tiver a coluna `words` (bancos muito antigos), ela é recalculada a
partir do texto.

## Áudios

Os áudios referenciados são **copiados** para a árvore do backend
(`audio/AAAA/MM/`), com modo `0600`; colisões de nome recebem sufixo. Arquivos
ausentes não interrompem a importação — eles entram na contagem de “áudios
ausentes”. Se os caminhos gravados não existirem mais, use `--audio-dir` para
apontar onde os arquivos estão hoje.

## Compatibilidade de endpoints

O app 1.x expõe `GET /api/health` e `POST /api/transcriptions`. A v1 do backend
usa `/api/v1/...`. Se algum cliente legado precisar continuar funcionando, os
caminhos antigos podem ser reintroduzidos como camada de compatibilidade antes
de removê-los.
