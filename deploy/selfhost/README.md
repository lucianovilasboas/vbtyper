# VB Typer — instalação self-hosted

Uma instância por pessoa: a API e a interface rodam no **seu** servidor, com o
**seu** domínio e a **sua** chave da OpenAI. O áudio e o histórico não passam por
terceiros.

## Requisitos

- Docker com Compose v2;
- (modo público) um domínio apontando para a máquina e as portas **80/443**
  liberadas — o Caddy emite o certificado sozinho;
- uma chave da OpenAI.

## Instalar

```bash
git clone https://github.com/lucianovilasboas/vbtyper.git
cd vbtyper/deploy/selfhost
./install.sh
```

O instalador pergunta o domínio, a chave, o fuso e **gera** o token da API e a
senha de acesso. No fim mostra a URL e as credenciais.

### Sem domínio (só nesta máquina)

```bash
./install.sh --local
```

Publica apenas em `127.0.0.1:8765`, sem senha e sem TLS. Serve para usar no
próprio computador (o microfone do navegador funciona em `localhost`).

### Só gerar o `.env`

```bash
./install.sh --no-start
docker compose --profile public up -d --build
```

## Como o acesso fica

| Caminho | Proteção |
|---|---|
| `/` — a página que entrega o cookie de sessão | **Basic Auth** (usuário e senha do instalador) |
| `/api/*` | **token** `Bearer` (o do `.env`) |
| `/sw.js`, `/manifest.webmanifest`, `/static/*` | público (é código e ícone; o service worker precisa disso) |

O Basic Auth **não** cobre `/api` de propósito: o cliente desktop usa
`Authorization: Bearer`, e o Basic consumiria o mesmo cabeçalho.

## Cliente desktop

```bash
vb-typer-desktop --base-url https://seu.dominio
```

E copie o `VB_TYPER_API_TOKEN` do `.env` para `~/.config/vb-typer/api-token`
(permissão `0600`).

## Operação

```bash
docker compose ps                       # estado
docker compose logs -f --tail=100       # logs
docker compose restart                  # reiniciar
docker compose down                     # parar (os dados ficam)
```

**Backup** (banco + áudios):

```bash
docker compose exec api tar czf - -C /data . > vb-typer-$(date +%F).tar.gz
```

**Restaurar**: pare, suba de novo e extraia o arquivo em `/data`:

```bash
docker compose down && docker compose up -d
docker compose exec -T api tar xzf - -C /data < vb-typer-2026-10-21.tar.gz
docker compose restart
```

**Atualizar**:

```bash
git pull
docker compose --profile public up -d --build     # modo público
# ou: docker compose up -d --build                # modo local
```

> Para atualizar **não** rode o instalador de novo: ele regravaria o `.env`
> (chave e credenciais). O `git pull` + `up --build` é suficiente.

## Limites conhecidos

- **Uma réplica**: SQLite e o worker de jobs no mesmo processo.
- O Basic Auth é um portão **temporário** de instância única: se um dia houver
  login multiusuário, ele sai.
- O modo público precisa de TLS para o microfone do navegador; em `http://` o
  navegador só libera o microfone em `localhost`.
