# vb-typer (cliente desktop)

Ditado por voz por atalho global no Linux/X11, consumindo a API REST local do
VB Typer. O texto é **inserido no ponto do cursor** do aplicativo em foco — não
há área de transferência, nem colagem, nem ativação de janela.

## Uso

```bash
cd desktop
uv sync --extra dev
uv run vb-typer-desktop              # sobe o ditado (bandeja e indicador)
uv run vb-typer-desktop --ui         # sobe e abre a interface no navegador
uv run vb-typer-desktop --status     # estado da API, do token e dos avisos
uv run vb-typer-desktop --self-test  # confere ambiente sem ditar
uv run vb-typer-desktop --write-preferences   # cria o arquivo de preferências
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

## Avisos na tela

O padrão é um **indicador visual silencioso**, desenhado logo acima da base da
janela em foco — no terminal, cai junto do prompt onde o texto vai aparecer:

| Fase | Desenho |
|---|---|
| Gravando | onda roxa reagindo ao nível real do microfone |
| Transcrevendo | barra laranja varrendo |
| Inserido | ✓ verde, ~1 s |
| Erro | ! vermelho, ~3 s |

Ele não tem fundo, não rouba foco e deixa os cliques atravessarem — nunca
atrapalha o aplicativo em uso. Não aparece em tela cheia.

Quem decide o visual é o cliente; o helper (`tray/indicator.py`) só desenha o que
recebe pelo socket de controle.

A onda vem do **nível real do microfone** (`arecord -V mono`), não de uma
animação: a captura usa `--period-size=256` para o nível sair a cada ~17 ms em vez
de ~140 ms. O painel aparece em ~60 ms (consulta ociosa) e, já visível, consulta a
cada 45 ms.

### Preferências

`~/.config/vb-typer/desktop.json` (criado por `--write-preferences`):

| Chave | Padrão | Valores |
|---|---|---|
| `notices` | `indicator` | `indicator`, `balloons` (balões do sistema, comportamento antigo), `both`, `none` |
| `anchor` | `window` | `window`, `screen` (canto da tela), `pointer` (perto do mouse) |
| `position` | `bottom-center` | `bottom-center`, `bottom-left`, `bottom-right`, `top-center` |
| `sound` | `false` | som nos balões que ainda existirem |
| `size` | `40` | altura do painel em pixels (24 a 96) |
| `speed` | `1.0` | quão rápido a onda reage e volta (0.5 a 3.0) |
| `sensitivity` | `1.0` | quão altas ficam as barras para a mesma voz (0.5 a 3.0) |

Se a onda parecer lenta, suba `speed`; se as barras parecerem baixas, suba
`sensitivity`. Mudanças valem no próximo start.

Para voltar ao comportamento antigo sem editar arquivo:

```bash
uv run vb-typer-desktop --notices balloons
```

Diagnóstico do indicador (ele não tem terminal para reclamar):

```bash
VB_TYPER_INDICATOR_DEBUG=/tmp/indicador.log uv run vb-typer-desktop
```

## Decisões que valem saber

- **Sem `pynput` no Linux.** O listener de eventos do XRecord não encerra de forma
  confiável: o `stop()` retorna, mas a thread de escuta continua viva — e cada
  pausa deixaria um contexto X pendurado no servidor. O atalho é observado
  consultando `XQueryKeymap` a cada 25 ms: determinístico, para na hora e não
  custa nada perceptível para um atalho de segurar. No Windows/macOS o adaptador
  equivalente usa `pynput`.
- **A interface é a SPA no navegador**, não Tk. O cliente cuida só da integração
  com o sistema (atalho, microfone, inserção, bandeja, indicador) e abre a
  interface em modo app quando há Chromium/Chrome; sem ele, abre uma janela nova
  no Firefox.
- **`arecord` leva ~300 ms para abrir o dispositivo.** Numa gravação curta, os
  primeiros instantes podem faltar. É o mesmo comportamento do 1.x, que usa o
  mesmo comando.
- **Janela POPUP e `Gtk.Window.resize`.** Uma janela `POPUP` se dimensiona pelo
  pedido do filho: sem `set_size_request` no `DrawingArea` o GTK mapeia num
  tamanho padrão e o painel sai gigante.
- **O período da captura define a vida da onda.** O medidor do `arecord` sai a
  cada período de captura: o padrão dava ~7 atualizações por segundo (140 ms) e
  deixava a onda lenta, por melhor que fosse a animação. Com
  `--period-size=256` são ~58 por segundo (17 ms). Se algum dispositivo reclamar
  de *xrun*, 512 (32 ms) é o meio-termo.
- **Suavização em constante de tempo, não por quadro.** A onda sobe em ~35 ms e
  volta em ~100 ms, independente da taxa de quadros — antes eram frações fixas
  por quadro, o que amarravam o comportamento à taxa de desenho.
- **Posição vem do cliente, não do helper.** A escolha de âncora e o recorte na
  tela são cálculo puro (`geometry.py`, testado); o desenho de fato só se
  verifica no olho, numa sessão X11.

## Arquitetura

| Módulo | Papel |
|---|---|
| `daemon.py` | máquina do ditado: atalho, gravação, job, inserção, avisos |
| `api.py` | cliente REST e leitura do token (`~/.config/vb-typer/api-token`) |
| `audio.py` | `arecord`, medição de nível, validação e reparo do WAV |
| `hotkey.py` | máquina de estados do Ctrl+Super |
| `geometry.py` | posição do indicador (cálculo puro, sem X e sem GTK) |
| `preferences.py` | preferências do cliente |
| `control.py` | socket Unix usado pelos helpers (`vb-typer-desktop-<uid>.sock`) |
| `tray.py` + `tray/tray_helper.py` | bandeja GTK3 em processo separado |
| `tray/indicator.py` | indicador visual (GTK3, também processo separado) |
| `ui.py` | abre a interface no navegador (modo app quando possível) |
| `platform/` | adaptadores por sistema; hoje só `linux_x11` |

Os dois helpers GTK rodam no **Python do sistema**, porque o PyGObject não
empacota bem no PyInstaller. O nome do socket é próprio (`vb-typer-desktop-…`)
para nunca conflitar com o app 1.x, que continua rodando em paralelo.

## Testes

```bash
cd desktop
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
```

Nenhum teste chama a OpenAI, abre microfone, conexão X ou rede: os dublês estão em
`tests/fakes.py`. A suíte inclui um teste de invariante que varre o código-fonte e
falha se aparecer qualquer chamada de área de transferência ou de ativação de
janela.

## Pendências

- Windows/macOS: a camada `platform/` está pronta para receber os adaptadores.
- Autostart no login e empacotamento one-file (PyInstaller).
