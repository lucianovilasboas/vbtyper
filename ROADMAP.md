# ROADMAP — VB Typer 2.0

Pendências combinadas com o Luciano. **Nada aqui está implementado**, exceto o
que estiver marcado como feito.

Última atualização: 20/10/2026 — tudo em `v0.8.1` (backend: 99 testes; desktop:
169 testes).

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

O cliente desktop também já lê a configuração e envia o modo, e a **bandeja**
ganhou os itens *Modo literal* / *Modo inteligente* (`v0.5.1`) — com o vigente
marcado no rótulo (itens de rádio foram descartados: ver a armadilha anotada no
`AGENTS.md`).

### Pendente — escolher o modelo do ajuste e ver o custo de cada etapa

**Pedido (Luciano, 19/10):** "só a possibilidade de poder configurar o modelo na
tela de configuração e de ver os custos separados quando o modelo for usado. E é
claro que o modelo só deve ser usado em caso de extrema necessidade para
economizar. E na hora de mostrar lá no histórico, deixar claro o valor de cada
etapa separada, pelo menos a estimativa, para eu ter esse controle dos gastos."

Nada disso muda o comportamento do ditado: é **controle de gasto**.

**O que existe hoje (verificado no código):**

- o ajuste usa `smart_model` da configuração (`core/config.py`, padrão
  `gpt-4o-mini`), e ele **não** está em `/api/v1/settings` — nem na leitura nem
  na escrita. Não há como trocar pela interface;
- o adaptador **ignora o campo `usage`** da resposta do chat: o custo do ajuste
  não é medido nem registrado. O "custo estimado" do histórico e da Atividade
  conta **só a transcrição**.

**Por que isso importa** (números de referência para uma fala de 20 s, ~60
palavras; tarifas públicas, sujeitas a mudança — conferir na implementação):

| Etapa | Custo |
|---|---|
| Transcrição (`gpt-4o-mini-transcribe`, US$ 0,003/min) | US$ 0,0010 |
| Ajuste com `gpt-4o-mini` (~80 tokens entrada + ~85 saída) | US$ 0,00006 (≈6%) |
| Ajuste com `gpt-4o` (US$ 2,50/M entrada, US$ 10/M saída) | US$ 0,0011 (**≈ o ditado inteiro**) |

Numa fala curta (5 s) o ajuste com um modelo caro passa de 100% do custo da
transcrição. Escolher o modelo no escuro é escolher o gasto no escuro.

**Parte 1 — modelo do ajuste selecionável**

- `app_settings.smart_model` (migração), com `allowed_smart_models` na
  configuração, no padrão do `model`/`allowed_models` que já existe;
- `/settings` passa a **expor** `smart_model` e a lista, e a **aceitar** a troca
  (validada);
- **correção embutida:** hoje o worker lê o modelo do ajuste do *ambiente*, não
  da configuração — o mesmo defeito já corrigido no modo. Resolver na origem (o
  job resolve a escolha vigente);
- na tela de Configurações, um combo com o modelo **e o preço ao lado** de cada
  opção, deixando claro que só afeta o modo inteligente;
- o cliente desktop não muda: quem aplica o modelo é o backend.

**Parte 2 — custo de cada etapa, separado**

- ler o `usage` da resposta do ajuste e guardar por ditado os tokens e o custo
  real (`adjust_cost_usd`), com a tabela de texto em `domain/pricing.py`, ao lado
  da de áudio;
- **histórico:** a coluna CUSTO com o total, e a conta aberta no bloco de detalhes
  que já existe nas linhas inteligentes — "transcrição US$ 0,0010 + ajuste
  US$ 0,0001 (123 tokens)";
- **Atividade:** o "custo estimado" passa a somar os ajustes, com a linha de apoio
  dizendo a parcela;
- **CSV:** as duas colunas de custo, para contabilidade.

**Gastar só quando necessário**

A heurística de pulo já existe (`services/normalize.py`): prosa sem número, data,
valor ou sigla não gasta a segunda chamada. Ao implementar isto, vale revisar se o
gatilho deve ficar **ainda mais restrito** — o pedido é usar o ajuste só em caso
de necessidade real.

**Decisões em aberto:** quais modelos oferecer (proposta: `gpt-4o-mini` como
padrão e `gpt-4o` como opção); duas colunas de custo ou total + detalhe; se a
parcela do ajuste entra no custo estimado da Atividade.

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
a ser o medidor — gradiente de nove paradas, envelope na onda em repouso, traço
reativo ao nível real do microfone, brilho de 20% e a linha central. Sem botões
próprios: quem abre e fecha o microfone é o gravador. Um único loop de animação,
pausado quando a aba Ditar não está visível, e canvas dimensionado por
`devicePixelRatio`.

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

### O que falta desta seção

**AppImage x86_64 feito.** `scripts/build-appimage.sh` gera o cliente one-file
com PyInstaller dentro de um AppImage executável diretamente. O token fica na
configuração do usuário; os helpers GTK e `arecord` continuam sendo dependências
do Linux Mint, conforme a arquitetura atual do cliente.

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
