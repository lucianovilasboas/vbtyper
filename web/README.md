# Cliente web (próxima fase)

Reservado para o front-end web do VB Typer.

Plano: consumir exclusivamente a API v1 (`backend/`), gravando áudio pelo
navegador (`MediaRecorder`) e enviando como `multipart/form-data` para
`POST /api/v1/transcription-jobs`. O histórico e as estatísticas vêm das mesmas
rotas usadas pelo cliente desktop, garantindo uma única fonte de verdade.

Nada de segredo aqui: a chave OpenAI permanece no backend. O cliente usa apenas
o token de acesso local.
