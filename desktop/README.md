# vb-typer (cliente desktop)

Ditado por voz por atalho global no Linux/X11, consumindo a API REST local do
VB Typer. O texto é **inserido no ponto do cursor** do aplicativo em foco — não
há área de transferência, nem colagem, nem ativação de janela.

## Uso

```bash
cd desktop
uv sync --extra dev
uv run vb-typer-desktop              # sobe o ditado (e a bandeja)
uv run vb-typer-desktop --ui         # sobe e abre a interface no navegador
uv run vb-typer-desktop --status     # estado da API e do token
uv run vb-typer-desktop --self-test  # confere ambiente sem ditar
```

Segure **Ctrl+Super** para gravar; solte **Ctrl** ou **Super** para transcrever e
inserir. A bandeja mostra o estado (desativado, ativo, gravando, transcrevendo) e
oferece *Abrir configurações*, *Iniciar/Parar ditado* e *Sair*.

Antes de usar, a API precisa estar no ar e com a chave configurada:

```bash
systemctl --user status vb-typer-api
cd ../backend && uv run vb-typer-api --setup
```

## Como funciona

```
atalho → arecord (WAV 16 kHz mono) → POST /api/v1/transcription-jobs
       → GET até o estado terminal → XTEST digita no cursor
       → PATCH /api/v1/transcriptions/{id} {inserted, insert_ms}
```

- Se o foco mudar antes da inserção, o texto **não** é digitado em lugar nenhum;
  fica preservado no histórico com `inserted=false`.
- Cancelar (pausar o ditado ou sair) envia `DELETE` e nada é inserido depois.
- Cancelar durante a gravação descarta o áudio local; nada é enviado.
- Se o `arecord` for interrompido, o cabeçalho RIFF é reparado antes do envio.

## Decisões que valem saber

- **Sem `pynput` no Linux.** O listener de eventos do XRecord não encerra de forma
  confiável: o `stop()` retorna, mas a thread de escuta continua viva — e cada
  pausa deixaria um contexto X pendurado no servidor. O atalho é observado
  consultando `XQueryKeymap` a cada 25 ms: determinístico, para na hora e não
  custa nada perceptível para um atalho de segurar. No Windows/macOS o adaptador
  equivalente usa `pynput`.
- **A interface é a SPA no navegador**, não Tk. O cliente cuida só da integração
  com o sistema (atalho, microfone, inserção, bandeja) e abre a interface em modo
  app quando há Chromium/Chrome; sem ele, abre uma janela nova no Firefox.
- **`arecord` leva ~300 ms para abrir o dispositivo.** Numa gravação curta, os
  primeiros instantes podem faltar. É o mesmo comportamento do 1.x, que usa o
  mesmo comando.

## Pendências

- Windows/macOS: a camada `platform/` está pronta para receber os adaptadores.
- Autostart no login e empacotamento one-file (PyInstaller).

| Módulo | Papel |
|---|---|
| `daemon.py` | máquina do ditado: atalho, gravação, job, inserção |
| `api.py` | cliente REST e leitura do token (`~/.config/vb-typer/api-token`) |
| `audio.py` | `arecord`, validação e reparo do WAV |
| `hotkey.py` | máquina de estados do Ctrl+Super |
| `control.py` | socket Unix usado pela bandeja (`vb-typer-desktop-<uid>.sock`) |
| `tray.py` + `tray/tray_helper.py` | bandeja GTK3 em processo separado |
| `ui.py` | abre a interface no navegador (modo app quando possível) |
| `platform/` | adaptadores por sistema; hoje só `linux_x11` |

O nome do socket é próprio (`vb-typer-desktop-…`) para nunca conflitar com o app
1.x, que continua rodando em paralelo.

## Testes

```bash
cd desktop
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
```

Nenhum teste chama a OpenAI nem toca em dados reais do usuário. A suíte inclui um
teste de invariante que varre o código-fonte e falha se aparecer qualquer chamada
de área de transferência ou de ativação de janela.

## Pendências

- Windows/macOS: a camada `platform/` está pronta para receber os adaptadores.
- Autostart no login e empacotamento one-file (PyInstaller).
