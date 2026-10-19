# Implantação em contêiner — API + interface web

Um contêiner só serve a API REST **e** o webapp: a API já entrega o `index.html`
e os estáticos **na mesma origem**, então não há proxy interno, CORS entre
serviços nem build de front.

O **cliente desktop fica de fora**: ele precisa de X11, microfone e do cursor
local (ver `AGENTS.md`). Ele passa a apontar para este servidor.

> **Antes de expor:** ainda **não há login**. Em `127.0.0.1` isso é seguro; em
> qualquer endereço alcançável por terceiros, quem chega em `/` **recebe um
> cookie de sessão válido**. Por isso a porta é publicada apenas na interface
> **ZeroTier** (ou no loopback, para túnel SSH) — nunca em `0.0.0.0`.

## Subir

```bash
cd deploy/docker
cp .env.example .env
# edite .env: OPENAI_API_KEY, VB_TYPER_API_TOKEN, VB_TYPER_BIND_ADDR,
#            VB_TYPER_ALLOWED_HOSTS e VB_TYPER_CORS_ORIGINS

docker compose up -d --build
docker compose ps                      # deve mostrar "healthy"
curl http://127.0.0.1:8765/api/v1/ready
```

Descubra o endereço da ZeroTier no host e use-o nos três campos de acesso:

```bash
ip -4 -brief addr show | grep -E 'zt|10\.|172\.'   # interface ztXXXX
# ou: sudo zerotier-cli listnetworks
```

Com o endereço `10.147.20.5`, o `.env` fica:

```ini
VB_TYPER_BIND_ADDR=10.147.20.5
VB_TYPER_ALLOWED_HOSTS=127.0.0.1,localhost,10.147.20.5
VB_TYPER_CORS_ORIGINS=http://10.147.20.5:8765
```

`ALLOWED_HOSTS` e `CORS_ORIGINS` são validações distintas: a primeira checa o
cabeçalho `Host`, a segunda o `Origin`. Esquecer a segunda faz o webapp
responder **403 `invalid_origin`** ao ditar, mesmo com a página abrindo.

## Operação

```bash
docker compose logs -f --tail=100     # acompanhar
docker compose restart                # reiniciar
docker compose down                   # parar (o volume COM os dados fica)
docker compose up -d --build          # atualizar após um git pull
```

O banco e os áudios vivem no volume `vb-typer-data` (`/data`), com o **nome
fixo** — o backup não depende do nome do projeto.

## Se o Docker reclamar do pool de rede

Em host com muitos projetos, o Docker pode esgotar os endereços internos e o
`up` falha com *"all predefined address pools have been fully subnetted"*.
Contorne com um `docker-compose.override.yml` ao lado deste arquivo (não suba
esse arquivo junto se não precisar):

```yaml
networks:
  default:
    ipam:
      config:
        - subnet: 10.77.77.0/24   # escolha uma faixa livre no host
```

Confira antes se a faixa está livre:
`docker network ls` e, para cada rede, `docker network inspect <nome>`.

## Backup e restauração

```bash
# backup
docker compose exec api tar czf - -C /data . > vb-typer-$(date +%F).tar.gz

# restauração (sobrescreve; pare antes)
docker compose down
docker compose up -d
docker compose exec -T api tar xzf - -C /data < vb-typer-2026-10-19.tar.gz
docker compose restart
```

## O que o contêiner precisa (e por quê)

Levantado no código — cada item é uma armadilha real:

| Variável | Motivo |
|---|---|
| `VB_TYPER_WEB_DIR=/app/web` | o padrão procura `web/` pelo layout do repositório (`parents[3]`); na imagem isso não existe e **a interface não sobe** |
| `VB_TYPER_HOST=0.0.0.0` | é a autorização explícita que o `AGENTS.md` exige; vale **dentro** do contêiner, com a porta publicada só na ZeroTier |
| `VB_TYPER_ALLOWED_HOSTS` | `Host` é validado (a porta é ignorada); loopback já entra sozinho |
| `VB_TYPER_CORS_ORIGINS` | sem ela, o `Origin` do navegador fora do loopback leva **403** |
| `VB_TYPER_DATA_DIR=/data` | banco **e** áudios; sem volume, cada `up` perde tudo |
| `VB_TYPER_CONFIG_DIR=/data/config` | mantém qualquer estado fora do sistema de arquivos efêmero |
| `VB_TYPER_API_TOKEN` | evita o arquivo de token com estado; é o valor que o desktop guarda |
| `OPENAI_API_KEY` | o ambiente tem precedência; **não há cofre na imagem**, então `--setup` não se aplica |

As **migrações rodam sozinhas** no start (`vb_typer.main:create_app`), e o
`HEALTHCHECK` usa `/api/v1/health`, que é pública.

## Limites conhecidos

- **Uma réplica.** SQLite com o worker de jobs no mesmo processo: não use
  `--scale`, e um ditado longo atrasa os demais.
- **`/docs` e `/api/v1/openapi.json` são públicos** e fixos no código. Com a
  ZeroTier isso não sai da rede privada; ao abrir porta pública, desligue.
- **O cookie de sessão não tem `Secure`** — irrelevante aqui (sem TLS), a
  corrigir quando houver proxy HTTPS.
- **Sem limite de tentativas** de acesso: mais um motivo para não expor.

## Cliente desktop apontando para o servidor

O desktop continua fazendo a **inserção no cursor local**; só a API é remota:

```bash
uv run vb-typer-desktop --base-url http://10.147.20.5:8765
```

E o token: copie o `VB_TYPER_API_TOKEN` para `~/.config/vb-typer/api-token`
(permissão `0600`). No serviço de usuário, acrescente o `--base-url` ao
`ExecStart` em `~/.config/systemd/user/vb-typer-desktop.service`.

O áudio passa a subir pela rede — vale saber ao ditar em rede lenta.
