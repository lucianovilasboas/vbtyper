#!/usr/bin/env bash
# =====================================================================
# Deploy do VB Typer na VPS (Traefik compartilhado, rede "proxy").
#
# Roda na raiz do projeto, no servidor:
#     ./deploy.sh              # git pull + build + subida + healthcheck
#     ./deploy.sh --no-pull    # sem git pull (só rebuild/recreate)
#
# Só sobe; nunca derruba o volume (nada de `down -v`). Se o contêiner não
# ficar saudável, mostra o log e sai com erro, sem rollback automático —
# esconder a causa de um build quebrado custa mais caro do que ver o log.
# =====================================================================

set -euo pipefail

cd "$(dirname "$0")"

COMPOSE_FILE="deploy/docker/docker-compose.vps.yml"
ENV_FILE="deploy/docker/.env"
HEALTH_TIMEOUT=180
PULL=1

for arg in "$@"; do
  case "$arg" in
    --no-pull) PULL=0 ;;
    -h|--help)
      sed -n '3,10p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Argumento desconhecido: $arg" >&2
      exit 2
      ;;
  esac
done

fail() {
  echo "ERRO: $*" >&2
  exit 1
}

command -v docker >/dev/null 2>&1 || fail "docker não encontrado"
docker compose version >/dev/null 2>&1 || fail "docker compose v2 não encontrado"
docker network inspect proxy >/dev/null 2>&1 \
  || fail "a rede externa 'proxy' não existe — é dela que o Traefik fala com o app"
[ -f "$COMPOSE_FILE" ] || fail "não achei $COMPOSE_FILE (rode a partir da raiz do projeto)"
[ -f "$ENV_FILE" ] || fail "não achei $ENV_FILE — copie de deploy/docker/.env.vps.example"

perm=$(stat -c '%a' "$ENV_FILE")
[ "$perm" = "600" ] || echo "AVISO: $ENV_FILE está com permissão $perm (o esperado é 600)"

COMPOSE=(docker compose -f "$COMPOSE_FILE")
DOMAIN=$(grep '^VB_TYPER_DOMAIN=' "$ENV_FILE" | head -1 | cut -d= -f2 || true)

if [ "$PULL" = "1" ]; then
  command -v git >/dev/null 2>&1 || fail "git não encontrado"
  before=$(git rev-parse --short HEAD)
  echo "== git pull (estava em $before)"
  git pull --ff-only
  echo "== commit: $before -> $(git rev-parse --short HEAD)"
else
  echo "== git pull ignorado (--no-pull)"
fi

echo "== build e subida"
"${COMPOSE[@]}" up -d --build

echo "== aguardando ficar saudável (até ${HEALTH_TIMEOUT}s)"
status=""
deadline=$((SECONDS + HEALTH_TIMEOUT))
while [ "$SECONDS" -lt "$deadline" ]; do
  status=$(docker inspect vbtyper_api --format '{{.State.Health.Status}}' 2>/dev/null || true)
  [ "$status" = "healthy" ] && break
  sleep 3
done

if [ "$status" != "healthy" ]; then
  echo "ERRO: o contêiner não ficou saudável (estado: ${status:-desconhecido})" >&2
  echo "--- últimas 60 linhas do log ---" >&2
  "${COMPOSE[@]}" logs --tail=60 api >&2 || true
  echo >&2
  echo "Para voltar à versão anterior:" >&2
  echo "  git checkout <tag> && ./deploy.sh --no-pull" >&2
  exit 1
fi

echo
echo "== no ar"
echo "   commit:    $(git rev-parse --short HEAD) · $(git log -1 --pretty=%s)"
echo "   container: $(docker inspect vbtyper_api --format '{{.State.Health.Status}}')"
echo "   url:       https://${DOMAIN:-<domínio não definido no .env>}"
"${COMPOSE[@]}" ps
