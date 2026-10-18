# Clientes desktop (próxima fase)

Reservado para os aplicativos desktop Linux, macOS e Windows.

Plano: cada cliente mantém só o que é local à plataforma — captura de microfone,
atalho global, inserção de texto e (opcional) bandeja — e fala com a API v1.

- Linux: atalho X11 e inserção via XTEST (como no app 1.x).
- macOS: atalho de sistema e inserção via `CGEvent`/Accessibility.
- Windows: atalho global e inserção via `SendInput`.

Todos enviam áudio para `POST /api/v1/transcription-jobs`, exibem o resultado e
reportam a inserção por `PATCH /api/v1/transcriptions/{id}`.
