# ROADMAP — VB Typer 2.0

Pendências combinadas com o Luciano. **Nada aqui está implementado**, exceto o
que estiver marcado como feito.

Última atualização: 24/10/2026 — tudo em `v0.17.2` (backend: 167 testes; desktop:
242 testes).

---

## 1. Modos de transcrição: literal, inteligente e estruturado

**Pedido (Luciano, 18/10):** oferecer três modos de transcrição.

- **Literal:** preserva exatamente as palavras reconhecidas.
- **Inteligente:** converte datas, números, valores e siglas para formatos
  convencionais.
- **Estruturado:** extrai entidades específicas e devolve um JSON conforme um
  esquema definido pelo usuário.

### Literal e Inteligente: **feito em `v0.5.0`**

O padrão continua sendo **literal**; o Inteligente só entra quando o usuário
escolhe (tela de Configurações ou campo `mode` no job). O que foi implementado:

- coluna `mode` no job, no histórico e nas configurações; `raw_text` guarda o
  texto reconhecido, para auditar o ajuste e poder voltar atrás (migração
  `0002_modes`);
- o Inteligente é uma segunda chamada (`/chat/completions`), com a instrução em
  `services/normalize.py`, validada contra a API real: "dezoito de outubro de
  dois mil e vinte e cinco às três e meia da tarde" → **18/10/2025 às 15h30**,
  "cinquenta reais e vinte centavos … trinta por cento" → **R$ 50,20 … 30%**,
  "o c p v … c p f" → **CSV … CPF**;
- **pulo por heurística:** texto sem número/data/valor/sigla não gasta a segunda
  chamada (prosa comum sai com a latência de hoje). A checagem é conservadora:
  um falso "sim" custa latência, um falso "não" custaria o formato pedido;
- **falha do ajuste entrega o literal** (nunca perde o ditado) e registra no log;
- **conexão reaproveitada** no adaptador da OpenAI: antes cada ditado abria um
  cliente HTTP novo, pagando um handshake TLS;
- a dica curta de formatação (`prompt`) só vai na transcrição quando o modo é
  smart — no literal nada enviesa o reconhecimento.

O cliente desktop também já lê a configuração e envia o perfil, e a **bandeja**
passou a listar os **perfis de texto** (`v0.5.1` trouxe os modos, substituídos
pelos perfis agora) — com o vigente marcado no rótulo (itens de rádio foram
descartados: ver a armadilha anotada no `AGENTS.md`). A lista é relida de tempos
em tempos, então perfis criados ou apagados na interface aparecem sem reiniciar.

### Perfis de texto: **feito em `v0.12.0`** (backend + web; Linux feito)

Dez perfis padrão — literal, revisado, e-mail, WhatsApp, programação, prompt,
acadêmico, currículo, carta e ata — mais perfis personalizados. Todos vivem no
banco: os padrões são semeados uma única vez e podem ser editados, duplicados ou
removidos; só a transcrição fiel não pode ser excluída (é a base do ditado e o
fallback do perfil padrão). A transcrição fiel fica em
`transcriptions.raw_text` e é a **fonte de toda versão editorial**:
`transcription_versions` guarda cada geração com texto, modelo, tokens e custo, e
a conversão nunca parte de uma versão já editada. O job aceita `profile` (`mode`
continua como alias para o desktop), `/settings` ganhou `default_profile` e
`POST /transcriptions/{id}/render` gera outra versão sem re-transcrever o áudio.
Na web: seletor na aba Ditar, cartão de perfis nas Configurações e seletor de
versões (mais "gerar versão") no Histórico. No cliente Linux, o job passa a
enviar `profile` e a bandeja lista os perfis; macOS/Windows ficam para depois.

**Selects e fases (`v0.12.1`).** Modelo, idioma e perfil são trocados direto na
linha "Ditando com"; a linha de status acompanha a fase real do job
(transcrevendo → montando o e-mail → pronto) pela coluna `jobs.phase`.

**Destaques de "agora" (`v0.15.0`).** A Atividade marca em verde a hora, o dia e o dia
da semana atuais: a barra da hora no gráfico por hora (ou um traço na base quando
ainda não há ditado), a coluna do dia da semana, a célula de hoje no heatmap de
consistência e o ponto do dia/mês no volume e no ritmo de fala. A legenda mostra
"agora: sábado, 24/10 · 11h". O `/stats` passou a devolver `now` (horário local do
servidor) para o destaque não depender do relógio do navegador, e a virada de hora
recarrega a tela pelo poll que já existia.

**Atalhos de perfil (`v0.16.0`).** O cliente desktop troca de perfil pelo teclado:
`Ctrl+Alt+Tab` avança, `Ctrl+Alt+Shift+Tab` volta e `Ctrl+Alt+0` retorna ao padrão. A
troca é temporária (não mexe no `default_profile`) e o indicador mostra o nome do perfil.
As combinações ficam em `app_settings.hotkeys`, editáveis na nova seção
**Configurações › Atalhos**, com captura pelo teclado e validação no backend (recusa
Ctrl+Super, que é o atalho de gravar). No X11 o grab (`XGrabKey`) impede que a combinação
chegue ao aplicativo em foco.

**Ditado contínuo (`v0.17.0`).** Cada perfil pode ser marcado como contínuo: a segunda
chamada passa a receber os ditados anteriores como contexto (últimos 3, até 45 min,
~3.000 caracteres, só o texto entregue e sem erro) para o texto continuar o raciocínio
sem repetir o que já está no documento. O contexto serve **só** para continuidade — não
é reescrito nem resumido —, a opção é por perfil (a transcrição fiel ignora, porque não
tem segunda chamada) e falhar ao montar o contexto nunca derruba o ditado. O histórico
marca "contínuo" nos ditados que usaram memória (`transcriptions.continuity_count`).

**Continuidade sem repetição (`v0.17.1`).** As regras de continuidade passaram para o
**fim** do prompt (vencem as do perfil) e dizem explicitamente para descartar a
reafirmação de ideia, fato ou número já escrito — nomes e termos continuam permitidos
quando a frase precisa. Se o ditado não acrescentar nada, o modelo responde
`[nada novo]`: o job conclui sem texto, nada é inserido e o cliente mostra "nada novo"
(com `text` vazio no histórico, em vez de erro ou de o literal repetido). O prompt foi
verificado com chamadas reais em quatro cenários (continuação, repetição parcial,
repetição total e assunto sem relação) — a checagem ficou em
`scripts/verify-continuity.py` para poder ser repetida.

**"Nada a acrescentar" em vez de erro (`v0.17.2`).** Com o texto vazio (ditado que só
repetia), o cliente antigo acusava "A API não reconheceu fala"; agora o job conclui sem
texto e o cliente avisa **"nada a acrescentar"** (fase própria do indicador, sem balão
de erro). O backend também aceita resposta **vazia** do modelo quando há contexto de
continuidade (antes virava erro e caía no literal repetido); sem contexto, vazio
continua sendo falha do ajuste.

### Modelo do texto e itens de perfil: **feito em `v0.13.0`**

O modelo da segunda etapa deixou de vir só do ambiente: `app_settings.smart_model`
(migração `0006`) é exposto e aceito em `/settings`, com a lista de autorizados e
**o preço por 1M ao lado de cada opção**. Cada perfil pode fixar o seu modelo
(`options.modelo`), que vence o global. A resolução passou a ler o banco nos dois
caminhos (worker e render); o custo da versão já usava o modelo efetivo.

Perfis personalizados ganharam **regras/itens** (`options.items`, até 12), que
entram no prompt como bloco próprio ("Regras deste perfil") — o usuário define a
ação e as restrições sem escrever um prompt inteiro. Os quatro modelos de texto
foram verificados na API real (21/10/2026).

### Ferramentas de texto e destinos: **feito em `v0.19.0`**

O pipeline de perfis ganhou transformações determinísticas
(`domain/text_tools.py`) com fases `before`/`after`: `strip_ansi`,
`strip_control`, `spaces_for_tabs`, `single_line`, `trim` e `strip_markdown`. O
perfil declara um **destino** (`options.delivery`: `text` ou `tui`) e
ferramentas extras (`tools`/`tools_before`); o destino é um preset semântico —
TUI é um destino, não a regra — e pode ganhar outros (markdown, code, shell) sem
mexer no worker.

O worker e o render aplicam `tools_before` antes da segunda chamada e
`tools` + preset do destino depois; o perfil literal também pode usar (o
`raw_text` continua intacto). A transcrição guarda `delivery` e `tools` efetivos
(migração `0010`). O cliente desktop aplica um guard por destino antes do XTEST
(TUI: uma linha, sem Tab/ESC); o web mostra o selo do destino e o editor de
perfis tem o select **Destino do texto** + **Remover Markdown**. Não há tool
calling da LLM: as transformações são determinísticas.

### Estruturado: pendente, e é o que falta decidir

Continua como estava: **não** vai para o cursor (devolve um documento, para a
tela e o histórico), exige **duas etapas** (a transcrição não aceita esquema
JSON) e depende de duas decisões do Luciano:

1. o esquema é **colado como JSON** ou montado por um **construtor de campos**?
2. esquemas nomeados ("despesa", "reunião", "tarefa") para escolher ao ditar?

Fases: colunas de esquema e resultado estruturado → validador que transforma o
esquema do usuário em formato *estrito* aceito pela OpenAI → tela para ver,
copiar e baixar o JSON → exportação.

### Opcionais registrados

- **Cache do ajuste por texto** (tabela pequena com validade): acerta quando se
  repete uma frase; ganho baixo, custo baixo.
- **Cache do resultado da transcrição**: não faz sentido (dois ditados nunca são
  iguais).
- O áudio já é arquivado localmente, o que cobre a outra metade (reenvio).

### O ponto de arquitetura que precisa ficar claro

São **dois tipos de coisa**, não três variantes do mesmo:

| Modo | O que sai | Onde isso vive |
|---|---|---|
| Literal | texto | no cursor (como hoje) |
| Inteligente | texto normalizado | no cursor |
| Estruturado | **JSON** | **não** no cursor — nas telas do app e no histórico |

Não faz sentido inserir JSON no meio de um e-mail. O modo Estruturado devolve um
**documento**: ele pertence à interface (ver, copiar, baixar) e ao histórico, não
ao fluxo de inserção no cursor. Vale confirmar isso com o Luciano.

### O que a API da OpenAI permite

- O endpoint de transcrição **não aceita esquema JSON** (`response_format` só tem
  `text`/`json`/`srt`/`verbose_json`/`vtt`). Logo o modo Estruturado exige **duas
  etapas**: transcrever e depois chamar `/chat/completions` com
  `response_format: json_schema` (Structured Outputs).
- O adaptador (`adapters/openai.py`) hoje faz transcrição (com `prompt`
  opcional), chat (`/chat/completions`, usado pelo ajuste) e a verificação de
  credencial (`/models`), com **conexão reaproveitada** entre chamadas.
- **Inteligente** usa os dois caminhos: o `prompt` curto na própria transcrição
  (grátis) **e** a segunda chamada com as instruções completas — que custa
  ~0,5–2 s de latência. É por isso que ela é pulada quando não há o que
  converter.
- *(feito em `v0.5.0`)*

### Onde encaixa no código atual

Pipeline de hoje: `POST /api/v1/transcription-jobs` →
`services/transcription.py::create_job` → `workers/manager.py::_process` chama
`openai.transcribe` → `finish_success(texto)`.

| Peça | Mudança | Estado |
|---|---|---|
| `db/models.py` → `jobs` | coluna `mode` | **feito** |
| `db/models.py` → `transcriptions` | `mode` e `raw_text` | **feito** |
| `db/models.py` → `transcriptions` | `structured_json` | falta (Estruturado) |
| migração Alembic | `0002_modes` | **feito** |
| `adapters/openai.py` | transcrição com `prompt`, chat e conexão reaproveitada | **feito** |
| API v1 | `mode` no `POST` de jobs; modo padrão em `/api/v1/settings` | **feito** |
| web | seletor nas Configurações, chip na tela Ditar, selo no Histórico | **feito** |
| cliente desktop | herda modelo, idioma e modo de `/settings` | **feito** |
| web | tela para ver, copiar e baixar o JSON | falta (Estruturado) |

**Guardar o texto cru sempre** (`raw_text`) é o que permite auditar, comparar e
desfazer: se o modo inteligente errar um valor, o original continua no histórico.

### Duas decisões de projeto a manter

1. **Falha na segunda chamada nunca perde o ditado.** Se o chat falhar (esquema
   recusado, cota, rede), o job entrega o **texto literal** e registra o motivo.
2. **O esquema do Estruturado é a parte cara.** Structured Outputs exige esquema
   *estrito* (todos os campos obrigatórios, `additionalProperties: false`, tipos
   suportados). O backend precisa **validar e normalizar** o que o usuário
   mandar, senão a chamada quebra.

### Fases

1. ~~Backend — literal + inteligente~~ (**feito**, `v0.5.0`), com os testes: os
   dois modos, o pulo por heurística, a falha do ajuste e o modo inválido.
2. ~~Web UI e cliente desktop~~ (**feito**): seletor nas Configurações, chip na
   tela Ditar, selo no Histórico e o modo enviado em cada ditado.
3. **Estruturado.** Esquemas **nomeados** (ex.: "despesa", "reunião", "tarefa"),
   validador/normalizador de esquema, o JSON na tela (bonito, copiar, baixar) e
   no histórico, exportação em CSV.

### Perguntas em aberto (para o Luciano)

1. **Estruturado:** confirma que **não** vai para o cursor? O esquema é **colado
   como JSON** ou montado por um **construtor de campos** (nome/tipo/descrição)?
2. **Modelo do ajuste e custo das etapas:** as decisões estão na subseção
   "Pendente — escolher o modelo do ajuste e ver o custo de cada etapa".

*(Respondidas e implementadas: segunda chamada com o `prompt` junto; falha do
ajuste entrega o literal.)*

---

## 2. Interface web com a cara do 1.x

**Feito em `v0.4.0`** (commit `a9e6013`). As quatro telas seguem o protótipo do
1.x (`hermes-workspace/vibe-typer/prototype-estatisticas.html`): paleta com o
roxo `#7839e8`, cartões, gráficos em SVG, mapa de consistência das últimas 13
semanas, uso por dia da semana, tabela de histórico com **custo por ditado** e
tela de configurações com miniatura de cada tema (claro/escuro/automático).

O custo por ditado vem da API (`cost_usd` em cada transcrição), calculado pela
tarifa do modelo em `domain/pricing.py` — uma fonte só, sem tabela duplicada no
JavaScript.

**Onda do microfone na aba Ditar** (`v0.7.0`): o efeito do demo `wave.js` passou
a ser o medidor — gradiente de nove paradas, **linha reta em repouso** (sem a
ondulação do demo), traço reativo ao nível real do microfone, brilho de 20% e a
linha central. Sem botões próprios: quem abre e fecha o microfone é o gravador.
O loop de animação só roda durante a gravação, é pausado quando a aba Ditar não
está visível, e o canvas é dimensionado por `devicePixelRatio`.

**Histórico no celular e horas na Atividade** (`v0.11.0`): abaixo de 720 px a
tabela de 6 colunas vira lista de cartões (rótulos curtos, texto em até 3 linhas,
sem rolagem lateral). A Atividade ganhou o cartão **Por hora do dia** — 24 baldes,
inclusive vazios, com o pico — e passou a abrir em **7 dias** por padrão.

### Enviar arquivo pela aba Ditar: **feito**

A aba Ditar ganhou o card **Enviar arquivo**: escolher ou arrastar um áudio
(WAV, MP3, M4A, OGG ou WebM, até 25 MB), conferir nome, tamanho e duração, e
confirmar antes de gastar a chamada. O arquivo entra no **mesmo** pipeline do
microfone — job, perfis, histórico, CSV e estatísticas —, e o texto cai no mesmo
campo para revisar e copiar. A duração vem dos metadados do próprio arquivo (o
backend só lê WAV), então arquivos longos passam a contar no custo e nas
estatísticas: o teto de sanidade da duração informada subiu de 2 min para 4 h e
o timeout do acompanhamento escala com a duração. O limite real continua sendo
o tamanho do arquivo (25 MB).

### O que falta desta seção

Duas análises que estavam no ROADMAP do 1.x e ainda não existem:

1. **Comparar a semana atual com a anterior**, com variação percentual de
   ditados, palavras e tempo de áudio. Sai quase de graça: são duas chamadas a
   `/stats` com intervalos diferentes (ou um parâmetro novo na API).
2. **Períodos de baixa atividade/pausas**, para acompanhar o padrão de uso — sem
   presumir que o app ativo significa que o usuário está disponível para ditar.

Ideias menores, se valerem: exportar também as estatísticas (hoje só o histórico
tem CSV) e um filtro de modelo na tela de atividade.

---

## 3. Cliente desktop: autostart e empacotamento

**Autostart feito em `v0.4.2`.** O cliente sobe no login por
`vb-typer-desktop.service` (unit de usuário), instalado com
`./scripts/install-desktop-service.sh`, que também grava a entrada no menu de
aplicativos com a marca. A unit declara `DISPLAY`/`XAUTHORITY` porque
`graphical-session.target` não é ativado no Cinnamon, e o cliente trata `SIGTERM`
para desmontar bandeja e indicador ao parar.

### Instalável: **feito em `v0.18.0`**

O cliente ganhou instalação sem terminal e configuração no primeiro uso:

- **primeiro uso:** diálogo GTK pede endereço e token, testa a conexão e grava o
  token em `~/.config/vb-typer/api-token` (0600); a URL vai para `desktop.json`.
  O token **não** é embutido no AppImage público. A bandeja ganhou
  **Configurar conexão…** para trocar URL/token sem reiniciar.
- **instalação:** `.deb` (duplo clique) e AppImage; os dois usam o mesmo binário
  PyInstaller (`scripts/build-binary.sh`). No AppImage, o primeiro uso oferece
  integrar ao sistema (menu + autostart) e copia para `~/.local/bin` para o
  caminho não quebrar na atualização.
- **autostart:** entrada XDG em `~/.config/autostart/vb-typer.desktop`; a unit
  systemd continua disponível para rodar a partir do código-fonte.
- **versionamento:** `VERSION` é a fonte única; `scripts/set-version.sh` sincroniza
  os pyprojects e `__version__`, e a tag `vX.Y.Z` precisa bater com ele.
- **release:** `.github/workflows/release.yml` gera AppImage + `.deb` +
  `sha256sums.txt` em tags `v*` (e artefatos avulsos no `workflow_dispatch`).

**O que falta:** macOS/Windows (seção 4), assinatura dos pacotes e auto-update.

### Latência do ditado: **feito** (branch `feat/latencia-do-ditado`)

O cliente passou a entregar o texto antes, sem tocar na configuração do servidor:

- **inserção em lotes** (`KEY_BATCH` = 16): `sync()`, foco e ponteiro uma vez por
  lote em vez de por tecla. Medido nesta máquina: **5,6 ms → 0,5 ms por
  caractere** no caminho bruto; um ditado de 1.280 caracteres cai de 9,6 s para
  menos de 1 s. **Revertido em `v0.20.1`** como padrão: em aplicativo com IBus o
  commit de uma tecla pode chegar depois da seguinte e o texto aparece trocado.
  O ritmo seguro (1 tecla, 4 ms) voltou a ser o padrão; o lote ficou opt-in e se
  prova com `scripts/type-probe.py`.
- **caracteres compostos**: `á`, `ã`, `é`… não existem no layout `br` e chegam
  por keycode reservado; eles e seus vizinhos forçam `sync()` + 6 ms de pausa,
  porque é o método de entrada que os recompõe.
- **menos idas e voltas**: as opções vêm do cache de 10 s (antes era um
  `GET /settings` por ditado), a primeira consulta do job é imediata e o
  intervalo dobra de 150 ms até 700 ms.
- **upload menor**: WAV → Opus 32 kbps quando a API é remota (~960 KB → ~120 KB
  em 30 s), com fallback obrigatório para o WAV; a duração medida vai junto no
  job.
- **modelo de fala**: o cliente pede `gpt-4o-mini-transcribe` (mais rápido) e cai
  para o padrão do servidor se a API recusar com `invalid_model`.
- **ritmo configurável**: `typing_batch`, `typing_delay_ms`, `upload_format` e
  `stt_model` no `desktop.json`, relido a cada 10 s (sem reiniciar).
- **medição**: `scripts/bench-dictation.py` (manual, gasta centavos) mostra o
  tempo por fase. Linha de base medida contra a VPS, áudio de 18,6 s e 580 KB:
  1,8 s de servidor e ~12 ms de envio.

**O que falta:** um modelo de texto por perfil pela API (`profiles.model` existe e
o worker respeita, mas `ProfileCreate`/`ProfileUpdate` não aceitam o campo — só
dá para mudar o modelo global das configurações). Só faz sentido depois de medir
o peso da segunda chamada com a fase `rendering` visível.

### Espelho entre bandeja e web: **feito** (branch `feat/espelhar-configuracoes`)

As escolhas do ditado passaram a ter um dono só — o servidor — e a chegar aos
dois lados em segundos:

- **bandeja** ganhou os submenus *Modelo de transcrição*, *Modelo de revisão* e
  *Idioma* (item vigente marcado no rótulo, sem `RadioMenuItem`), além dos perfis
  que já existiam. Cada clique grava em `PATCH /api/v1/settings` e o daemon adota
  a resposta na hora, então o ditado seguinte já usa a escolha nova.
- **sentido web → cliente**: o laço do daemon caiu de 10 s para **2 s** e passou a
  comparar a `version` publicada em `/settings` — só busca a lista de perfis e
  reaplica quando algo mudou. Menos tráfego que antes, mesmo assim mais rápido.
- **sentido cliente → web**: a página compara a mesma `version` a cada 2 s e
  re-renderiza selects e perfis. Se um campo estiver em edição, ela não atropela:
  recarrega a aba na próxima visita.
- **modelo**: o cliente deixou de impor `gpt-4o-mini-transcribe`. `stt_model` no
  `desktop.json` nasceu para resolver a latência e virou override vazio por
  padrão — quem manda é o modelo escolhido na web ou na bandeja.
- **versão**: a impressão digital inclui a lista de perfis, então renomear ou
  criar um perfil também se propaga.

Fora do escopo, por decisão: atalhos continuam sendo editados só na web; avisos,
forma da onda e ritmo da digitação continuam no `desktop.json` (são por
dispositivo e, num SaaS multiusuário, precisarão de tabela por cliente).

---

## 4. macOS e Windows

Pela camada `desktop/src/vb_typer_desktop/platform/`, que já existe e hoje só tem
`linux_x11`. Por sistema:

| Peça | Windows | macOS |
|---|---|---|
| Inserção | `SendInput` com `KEYEVENTF_UNICODE` (via `pynput`, que já faz isso) | CGEvent (exige permissão de Acessibilidade) |
| Áudio | `sounddevice` (não há `arecord`) | `sounddevice` |
| Bandeja | `pystray` | `rumps`/`pystray` |
| Notificações | toast nativo | Notification Center |
| Atalho | `pynput` (sem `pynput` no Linux, por causa do XRecord — ver AGENTS.md) | `pynput` |

Avisos: no Windows a tecla "Super" é a tecla Windows (risco de menu Iniciar /
`Win+L` — atalho configurável por SO); janelas elevadas não aceitam injeção
(UIPI); a paridade só se prova numa máquina Windows/macOS.

---

## 5. Pendências pequenas

- ~~**Ditados gravados pelo navegador ficam com `duration_s = 0`**~~ — **feito em
  `v0.6.1`.** O navegador passa a enviar `duration_s` (o cronômetro dele) e o
  backend só usa esse valor **quando a sonda do arquivo não sabe** — o WAV do
  desktop continua mandando, sem mudança de comportamento. Valor fora de faixa é
  ignorado: um palpite ruim nunca derruba o ditado. Junto disso: o histórico mostra
  **`—` em vez de `US$ 0,0000`** quando a duração é desconhecida (0 não é
  "grátis"), e a **duração média da Atividade** passou a dividir só pelos ditados
  com duração (`no_duration` no resumo). Os ditados antigos de WebM continuam sem
  duração — a informação nunca existiu e não há como recuperá-la.
- **3 linhas de teste no histórico** (ids 98, 99 e 100 — das minhas verificações
  do indicador, incluindo uma chamada real à OpenAI): **ficam**, por decisão do
  Luciano. Não apagar.
- Retorno do indicador recalibrado em `v0.4.1` (passou de exponencial para
  linear). Se ainda parecer lento no uso, `speed` no `desktop.json` — nada de
  código.

---

## 6. Serviço multiusuário (SaaS): contêiner, contas e login

**Decisão (19/10):** o projeto é **multiusuário** — a intenção é servir como SaaS
no futuro. Ordem combinada com o Luciano: **contêiner primeiro**; as demais
decisões depois.

### Etapa 1 — contêiner: **feito em `v0.6.0`**

`deploy/docker/` traz `Dockerfile`, `docker-compose.yml`, `.env.example` e
`README.md`; o `.dockerignore` (raiz) define o contexto, que precisa ser a raiz
para levar `backend/` e `web/`. **Um contêiner só serve API e webapp**: a API já
entrega o `index.html` e os estáticos na mesma origem, então não há proxy interno
nem build de front. O cliente desktop **não** é empacotado — precisa de X11,
microfone e do cursor local.

Verificado na máquina: build, `healthy`, webapp na raiz, `/api/v1/ready`, token
exigido (401), `Host` estranho (400), `Origin` permitida (200) e estranha (403), e
um ditado de ponta a ponta (job → worker → áudio no volume → falha limpa com
chave falsa, sem cobrança). Roda como usuário **não-root** (uid 10001), com os
dados em `0600`/`0700`.

**Decisão de exposição: ZeroTier.** Enquanto não houver login, a porta é
publicada apenas na interface ZeroTier (`VB_TYPER_BIND_ADDR`) — nunca `0.0.0.0`,
porque **quem alcança `/` recebe um cookie de sessão válido**.

**Implantação na VPS (`v0.8.0`).** `deploy/docker/docker-compose.vps.yml` roda
atrás do Traefik **compartilhado** da ovm-1 (rede `proxy`, resolver
`letsencrypt`, nenhuma porta publicada). Enquanto não há login, a **interface**
fica sob Basic Auth no Traefik; `/api/*` segue protegido pelo token do app — o
Basic consumiria o `Authorization: Bearer` do desktop. O cookie de sessão passou
a honrar `VB_TYPER_COOKIE_SECURE` atrás de TLS. Verificado com o domínio real:
`Host` e `Origin` aceitos, cookie `Secure`, 401 sem token, nenhuma porta no host.
O Basic Auth sai quando a etapa 2 (contas) entrar.

**Fuso do contêiner (`v0.8.1`).** O processo nasce em UTC no contêiner e, como o
banco guarda horário local (invariante 7), o histórico saía 3 h à frente. O compose
passou a definir `TZ` (`VB_TYPER_TZ`, padrão `America/Sao_Paulo`); as 28 linhas
gravadas antes da correção (14 transcrições e 14 jobs) foram ajustadas em −3 h,
com backup do banco antes.

**Defeito corrigido no caminho:** `VB_TYPER_ALLOWED_HOSTS`, `CORS_ORIGINS`,
`ALLOWED_MODELS` e `ALLOWED_CONTENT_TYPES` **não** funcionavam por ambiente — o
`pydantic-settings` tentava decodificar o valor como JSON **antes** do validador
`_split_csv`, e o processo morria no start. Resolvido com `NoDecode` (o formato
JSON continua aceito) e coberto por `tests/test_config.py`. Sem isso, o contêiner
não subiria configurado.

**Pendências para a exposição pública** (quando o login existir): desligar
`/docs` e `/api/v1/openapi.json` por configuração (hoje são públicos e fixos no
código); `Secure` no cookie de sessão sob TLS; limite de tentativas de acesso.
Melhoria sugerida: aceitar como origem o próprio `Host` quando ele passar em
`allowed_hosts` — hoje o endereço precisa ser repetido em `CORS_ORIGINS`, senão o
webapp leva 403 ao ditar.

### Self-hosted: **feito em `v0.14.0`** (alternativa ao SaaS)

`deploy/selfhost/` instala uma instância por pessoa com um comando: compose
próprio (sem depender do Traefik), **Caddy** com TLS automático e Basic Auth na
interface, e `install.sh` que pergunta domínio/chave/fuso e gera o token e a
senha. `/api`, `/static`, `/sw.js` e o manifest ficam fora do Basic (o service
worker precisa), como no Traefik. O modo `--local` publica só em `127.0.0.1`.

Verificado: 401/200 na frente do Caddy, API e service worker públicos, e o hash
bcrypt chegando intacto — o `env_file` do compose interpola `$`, então o
instalador dobra os cifrões.

### Etapa 2 — identidade e separação por conta

É a fundação do SaaS, e vai **junto com o login**: fazer a autenticação antes das
colunas de dono seria refazer consultas, armazenamento e testes depois.

| Peça | Hoje | Vira |
|---|---|---|
| `transcriptions` | tabela única | dono por linha |
| `jobs` | idem | dono por linha |
| `app_settings` | linha única `id=1` | uma por conta |
| áudios | `audio/AAAA/MM/…` | `audio/<conta>/AAAA/MM/…` |
| consultas a filtrar | — | **11 pontos** (`repositories/jobs` 2, `repositories/transcriptions` 4, `services/stats` 5) **+ todas as inserções** |
| autenticação | um token único em arquivo | sessões por pessoa + tokens por dispositivo |
| tabelas novas | — | `account`, `sessions`, `api_tokens` |

**Quem paga a OpenAI** é a pergunta que define o produto: um usuário que dite 2 h
por dia custa **~US$ 11/mês** só de transcrição (US$ 0,003/min), mais o ajuste do
modo inteligente. Plataforma pagando ⇒ **cotas obrigatórias desde o primeiro dia**
(por conta: minutos/mês, requisições/min, teto de custo); chave por conta (BYOK) ⇒
onboarding pior, mas sem risco financeiro, com a chave **cifrada em repouso**.

**Decisões em aberto (Luciano):**
1. quem paga a OpenAI — plataforma (com cotas) ou chave por conta (BYOK)?
2. cadastro **aberto** (exige email transacional: verificação e reset) ou **por
   convite** (conta criada por comando, **sem dependência de email**)?
3. um endereço só, ou **subdomínio por conta** (muda cookie de sessão,
   certificado wildcard e `allowed_hosts`)?
4. **senha** (com `hashlib.scrypt`, sem dependência nova) ou **código por email**?

**Privacidade (LGPD):** ditado guarda **o que a pessoa fala**. Mínimo antes do
primeiro usuário de fora: consentimento, exclusão a pedido, prazo de retenção,
cifra em repouso (hoje os áudios ficam em claro no volume) e política escrita.
Afeta o esquema (expurgo por conta), então é mais barato decidir agora.

**Escala:** SQLite com o worker no mesmo processo = **uma réplica** e fila global
— um ditado longo atrasa os demais. Serve as primeiras dezenas de contas; não
construir em cima de "escala réplicas". Os repositórios já isolam o SQL, o que
facilita migrar para Postgres depois.
