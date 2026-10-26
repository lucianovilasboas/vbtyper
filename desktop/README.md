# vb-typer (cliente desktop)

Ditado por voz por atalho global no Linux/X11, consumindo a API REST local do
VB Typer. O texto é **inserido no ponto do cursor** do aplicativo em foco — não
há área de transferência, nem colagem, nem ativação de janela.

## Instalar (usuário final)

Baixe o instalador na página de **Releases** do GitHub:

- **`.deb` (recomendado):** dê dois cliques e instale pelo Gerenciador de
  Arquivos/GDebi. O **VB Typer** aparece no menu de aplicativos.
- **AppImage:** permita a execução (Propriedades → Permissões) e abra. No
  primeiro uso, deixe marcado **Iniciar com o sistema** — no AppImage isso também
  integra o programa ao menu e copia o arquivo para um caminho estável.

No primeiro uso o cliente abre **Configurar conexão**: o endereço já vem
preenchido (`https://vbtyper.lucianovilasboas.com.br`) e você informa o token
da API. **Testar conexão** confere antes de salvar e **Iniciar com o sistema**
cria a entrada XDG do autostart. O token fica só na sua máquina, em
`~/.config/vb-typer/api-token` (modo `0600`), e **nunca** é embutido no AppImage
publicado.

O token é o mesmo `api-token` do servidor: peça a quem administra a instância
(ou, no servidor, `vb-typer-api --print-token`). O endereço pode ser trocado no
mesmo diálogo, para instâncias self-hosted. Depois, ele fica disponível em
**Bandeja → Configurar conexão…**.

## Uso

```bash
cd desktop
uv sync --extra dev
uv run vb-typer-desktop              # sobe o ditado (bandeja e indicador)
uv run vb-typer-desktop --ui         # sobe e abre a interface no navegador
uv run vb-typer-desktop --status     # estado da API, do token e dos avisos
uv run vb-typer-desktop --self-test  # confere ambiente sem ditar
uv run vb-typer-desktop --configure  # diálogo de URL e token (primeiro uso)
uv run vb-typer-desktop --write-preferences   # cria o arquivo de preferências
```

Segure **Ctrl+Super** para gravar; solte **Ctrl** ou **Super** para transcrever e
inserir. A bandeja mostra o estado (desativado, ativo, gravando, transcrevendo) e oferece
*Abrir configurações*, *Iniciar/Parar ditado*, o item **Perfis** — que abre o
submenu com os perfis de texto (o vigente com `✓`) — **Configurar conexão…** e
*Sair*.

O perfil escolhido pela bandeja é gravado no backend (`default_profile`), o mesmo
lugar onde a interface o edita — e a bandeja relê a configuração de tempos em
tempos, então uma troca feita na tela aparece no menu sozinha. Perfis criados ou
apagados na interface também aparecem/desaparecem sem reiniciar o cliente.

### Destino do texto

No editor de perfis da interface, **Destino do texto** pode ser **Texto normal**
(quebras de linha preservadas, para e-mail/ata) ou **Terminal (TUI)**: o backend
entrega o texto em uma linha, sem Tab/ESC/caracteres de controle, e o cliente
aplica uma guarda final antes do XTEST. Perfis com destino diferente de `text`
mostram o selo correspondente no histórico; o texto reconhecido continua
disponível em "ver o texto reconhecido". **Remover Markdown** é uma ferramenta
extra opcional do perfil.

### Trocar o perfil pelo teclado

| Atalho | Ação |
|---|---|
| **Ctrl+Alt+Tab** | próximo perfil |
| **Ctrl+Alt+Shift+Tab** | perfil anterior |
| **Ctrl+Alt+0** | volta ao perfil padrão |

A troca é **temporária**: vale para os próximos ditados e não altera o perfil
padrão gravado no backend — o atalho do padrão descarta o ciclo, e reiniciar o
cliente também. O indicador mostra uma **pílula com o nome em destaque** e a
posição na lista por ~1,6 s. Escolher um perfil pela bandeja (ou pela interface)
limpa o ciclo.

As combinações são editáveis em **Configurações › Atalhos** na interface web
(ficam no backend, não neste arquivo) e o cliente as aplica em até 10 segundos,
sem reiniciar. No Linux/X11 elas são *capturadas* com `XGrabKey`: o aplicativo em
foco não as recebe — sem isso, `Ctrl+Alt+Tab` trocaria de aba no navegador antes
de trocar o perfil. O atalho de gravar continua apenas observado.

No cliente instalado, a URL e o token são configurados pelo diálogo do primeiro
uso. Ao rodar a partir do código-fonte, a API local precisa estar no ar e com a
chave configurada:

```bash
systemctl --user status vb-typer-api
cd ../backend && uv run vb-typer-api --setup
```

## Rodar como serviço (autostart)

> Nas versões instaladas (`.deb`/AppImage), o autostart é uma entrada **XDG** em
> `~/.config/autostart/vb-typer.desktop`, criada pelo diálogo de configuração.
> A seção abaixo é para rodar a partir do código-fonte, com systemd.

Para o ditado subir sozinho no login, sem depender de terminal aberto:

```bash
./scripts/install-desktop-service.sh
```

O instalador grava a unit `vb-typer-desktop.service` (a partir de
`deploy/systemd/`), habilita no login, instala o ícone e cria a entrada no menu de
aplicativos. A unit roda `desktop/.venv/bin/vb-typer-desktop` com `DISPLAY` e
`XAUTHORITY` explícitos, reinicia em falha e — por causa do tratamento de
`SIGTERM` — desmonta bandeja e indicador quando o serviço para.

```bash
systemctl --user status vb-typer-desktop
journalctl --user -u vb-typer-desktop -f
systemctl --user restart vb-typer-desktop
systemctl --user disable --now vb-typer-desktop   # + rm a unit e o .desktop
```

Se você já tiver uma instância rodando por fora, encerre-a antes (menu *Sair* da
bandeja): o serviço detectaria a instância existente e apenas abriria a interface.

> A entrada do menu aponta para o mesmo binário. Com o serviço no ar, clicar nela
> não cria um segundo ditado — apenas abre a interface no navegador.

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
| Gravando | onda colorida, como o medidor da tela Ditar (o mesmo gradiente) |
| Transcrevendo | anel fino girando ao fundo + frase legível “Transcrevendo…” (e “Aplicando perfil…” quando há segunda chamada) |
| Inserido | ✓ verde, ~1 s |
| Erro | ! vermelho, ~3 s |

Ele não tem fundo, não rouba foco e deixa os cliques atravessarem — nunca
atrapalha o aplicativo em uso. Não aparece em tela cheia.

Quem decide o visual é o cliente; o helper (`tray/indicator.py`) só desenha o que
recebe pelo socket de controle.

A fase de gravação é a **mesma onda da tela Ditar**: linha colorida com o
gradiente do canvas web, desenhada a partir das amostras reais do microfone. Como
o `arecord` entrega o sinal cru (sem o AGC que o navegador liga), o helper aplica
um **ganho automático** — fala baixa sobe, fala forte não estoura e silêncio não
vira chiado — para a onda reagir como na web. Enquanto ainda não há amostras (o
começo da captura), desenha o envelope senoidal de repouso. Quem preferir a
**barra de nível** ancorada à esquerda, com trilho e preenchimento, usa
`"shape": "bar"`.

A onda vem do **áudio real**: o cliente envia a janela recente da captura
(512 quadros, 256 pontos) junto do estado, e o nível do medidor do `arecord`
continua alimentando a barra opcional. A captura usa `--period-size=256` para o
nível sair a cada ~17 ms em vez de ~140 ms. O painel aparece em ~60 ms (consulta
ociosa) e, já visível, consulta a cada 30 ms; o desenho roda a ~50 fps.

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
| `sensitivity` | `1.0` | quão altas ficam a onda e as barras para a mesma voz (0.5 a 3.0) |
| `shape` | `wave` | desenho da fase de gravação: `wave` (a onda da tela Ditar) ou `bar` (barra de nível) |

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
  deixava o nível lento, por melhor que fosse a animação. Com
  `--period-size=256` são ~58 por segundo (17 ms). Se algum dispositivo reclamar
  de *xrun*, 512 (32 ms) é o meio-termo.
- **A onda da web usa amostras, não o medidor.** O daemon lê a cauda do WAV em
  andamento (`Recorder.waveform`, 512 quadros) e manda 256 pontos no estado; o
  helper só desenha. A barra opcional (`shape: bar`) continua usando o nível.
- **Ganho automático na onda.** O `arecord` não tem o AGC que o `getUserMedia`
  liga; sem compensar, fala normal desenha quase uma reta. O helper acompanha o
  pico da janela (alvo ~60% da altura, no máximo 5×), reduz o ganho rápido e
  aumenta devagar, e ignora silêncio/chiado. `sensitivity` multiplica o resultado.
- **O "processando" é um anel girando com a fase escrita por cima.** A barra que
  deslizava lembrava a onda da gravação; um anel fino na borda (1,1 volta/s, a
  ~50 fps) fica ao fundo, e uma frase legível no centro diz o que o backend está
  fazendo: “Transcrevendo…” ou “Aplicando perfil…” (só quando há a segunda
  chamada). O texto tem contorno escuro para não sumir em fundo claro.
- **A troca de perfil é uma pílula de tamanho fixo.** O nome vai em negrito
  (~12,5 px) sobre um gradiente escuro com halo lilás, e a posição (“• 3/10” ou
  “• padrão”) abaixo; a pílula mede 184×32 e **não muda com o texto**, então
  trocar de perfil não move nada. A caixa do indicador fica mais larga (200 px)
  só nessa fase, e o flash dura 1,6 s. Nomes longos encolhem/reticenciam dentro
  da pílula; o resto do indicador continua transparente.
- **Sobe por constante de tempo, desce em linha reta.** A barra reage à voz em
  ~35 ms e volta a uma taxa fixa de 350%/s, zerando abaixo de 4%. O retorno
  linear é o ponto: uma exponencial deixa uma cauda longa nos últimos por centos,
  e é essa cauda que se percebe como lentidão. `speed` multiplica as duas coisas.
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
| `profile_switch.py` | ciclo de perfis e leitura das combinações (puro) |
| `geometry.py` | posição do indicador (cálculo puro, sem X e sem GTK) |
| `preferences.py` | preferências do cliente |
| `control.py` | socket Unix usado pelos helpers (`vb-typer-desktop-<uid>.sock`) |
| `tray.py` + `tray/tray_helper.py` | bandeja GTK3 em processo separado |
| `tray/indicator.py` | indicador visual (GTK3, também processo separado) |
| `ui.py` | abre a interface no navegador (modo app quando possível) |
| `platform/` | adaptadores por sistema; hoje só `linux_x11` |

### Ícones

Os ícones da bandeja (`assets/tray_*.png`) são a **marca do VB Typer** com a cor
de cada estado, todos em 64×64: `tray_on` (ditado ativo, cores originais),
`tray_rec` (lilás claro, o pulso da gravação), `tray_off` (vermelho, desativado),
`tray_busy` e `tray_busy_alt` (laranja, transcrevendo).

São **gerados** — não edite os PNG à mão:

```bash
cd desktop && uv run --with pillow python ../scripts/build-icons.py
```

O gerador lê a marca original em `vb-typer.png` (raiz do repositório) e também
escreve o logo e o favicon usados pelas telas do app em `web/static/`.

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

- Empacotamento one-file (PyInstaller), lembrando que a bandeja e o indicador
  continuam como helpers no Python do sistema.
- macOS e Windows pela camada `platform/` (fora do escopo atual).
