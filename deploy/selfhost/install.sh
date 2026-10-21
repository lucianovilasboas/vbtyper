#!/usr/bin/env bash
# =====================================================================
# VB Typer 2.0 — instalador self-hosted
#
#   ./install.sh              # público: domínio + Caddy (TLS automático)
#   ./install.sh --local      # só local: 127.0.0.1, sem domínio nem TLS
#   ./install.sh --no-start   # só gera o .env (não sobe nada)
#
# Requisitos: Docker + Docker Compose v2. No modo público, as portas 80/443
# precisam estar livres e o DNS do domínio apontando para esta máquina.
# =====================================================================

set -euo pipefail
cd "$(dirname "$0")"

MODE="public"
START=1

for arg in "$@"; do
  case "$arg" in
    --local) MODE="local" ;;
    --no-start) START=0 ;;
    -h|--help)
      sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'
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

# Prompt amigável no terminal e tolerante a entrada por pipe.
ask() {
  local prompt="$1" default="${2:-}" answer=""
  if [ -t 0 ]; then
    if [ -n "$default" ]; then
      read -r -p "$prompt [$default]: " answer
    else
      read -r -p "$prompt: " answer
    fi
  else
    read -r answer || true
  fi
  printf '%s' "${answer:-$default}"
}

ask_secret() {
  local answer=""
  if [ -t 0 ]; then
    read -r -s -p "$1: " answer
    echo >&2
  else
    read -r answer || true
  fi
  printf '%s' "$answer"
}

random_hex() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$1"
  else
    head -c "$1" /dev/urandom | od -An -tx1 | tr -d ' \n'
  fi
}

command -v docker >/dev/null 2>&1 || fail "docker não encontrado"
docker compose version >/dev/null 2>&1 || fail "docker compose v2 não encontrado"

if [ -f .env ]; then
  resposta=$(ask "Já existe um .env aqui. Sobrescrever? (s/N)" "N")
  case "$resposta" in
    s|S|y|Y) ;;
    *)
      echo "Nada foi alterado."
      exit 0
      ;;
  esac
fi

DOMAIN=""
if [ "$MODE" = "public" ]; then
  DOMAIN=$(ask "Domínio do app (ex.: vbtyper.seudominio.com)" "")
  DOMAIN="${DOMAIN#https://}"
  DOMAIN="${DOMAIN#http://}"
  DOMAIN="${DOMAIN%%/*}"
  [ -n "$DOMAIN" ] || fail "no modo público o domínio é obrigatório (use --local para instalar só na máquina)"
fi

OPENAI_KEY=$(ask_secret "Chave da OpenAI (sk-..., não aparece na tela)")
[ -n "$OPENAI_KEY" ] || fail "a chave da OpenAI é obrigatória"

HOST_TZ="UTC"
if [ -f /etc/timezone ]; then
  HOST_TZ=$(cat /etc/timezone)
elif command -v timedatectl >/dev/null 2>&1; then
  HOST_TZ=$(timedatectl show -p Timezone --value 2>/dev/null || echo "UTC")
fi
APP_TZ=$(ask "Fuso horário do app (o histórico usa horário local)" "$HOST_TZ")

API_TOKEN=$(random_hex 32)
BASIC_USER="admin"
BASIC_HASH=""
BASIC_PASS=""

if [ "$MODE" = "public" ]; then
  BASIC_PASS=$(random_hex 12)
  BASIC_HASH=$(docker run --rm caddy:2 caddy hash-password --plaintext "$BASIC_PASS" | tr -d '\r')
  [ -n "$BASIC_HASH" ] || fail "não consegui gerar o hash da senha de acesso"
  # O `env_file` do compose interpola `$`: sem dobrar, o hash bcrypt chega
  # truncado ao Caddy ("$2a$14"). Dobrado, chega literal.
  BASIC_HASH_ENV=${BASIC_HASH//\$/\$\$}
  HOSTS="$DOMAIN,127.0.0.1,localhost"
  CORS="https://$DOMAIN"
  SECURE="true"
  APP_URL="$DOMAIN"
else
  HOSTS="127.0.0.1,localhost"
  CORS=""
  SECURE="false"
  APP_URL=""
fi

umask 077
cat > .env <<EOF
# Gerado por install.sh em $(date '+%Y-%m-%d %H:%M')
# Não comite este arquivo: ele tem a chave da OpenAI e o token da API.
OPENAI_API_KEY=$OPENAI_KEY
VB_TYPER_API_TOKEN=$API_TOKEN

VB_TYPER_ALLOWED_HOSTS=$HOSTS
VB_TYPER_CORS_ORIGINS=$CORS
VB_TYPER_COOKIE_SECURE=$SECURE
VB_TYPER_TZ=$APP_TZ
VB_TYPER_LOCAL_PORT=8765

# Só no modo público (usados pelo Caddy)
VB_URL=$APP_URL
VB_TYPER_BASIC_USER=$BASIC_USER
VB_TYPER_BASIC_HASH=$BASIC_HASH_ENV
EOF
chmod 600 .env

if [ "$MODE" = "public" ]; then
  BACKEND="https://$DOMAIN"
  FRONTEND="https://$DOMAIN"
else
  BACKEND="http://127.0.0.1:8765"
  FRONTEND="http://127.0.0.1:8765"
fi

if [ "$START" = "1" ]; then
  echo
  echo "== construindo a imagem e subindo"
  if [ "$MODE" = "public" ]; then
    docker compose --profile public up -d --build
  else
    docker compose up -d --build
  fi

  echo "== aguardando ficar saudável (até 180s)"
  status=""
  deadline=$((SECONDS + 180))
  while [ "$SECONDS" -lt "$deadline" ]; do
    status=$(docker inspect vbtyper_api --format '{{.State.Health.Status}}' 2>/dev/null || true)
    [ "$status" = "healthy" ] && break
    sleep 3
  done

  if [ "$status" != "healthy" ]; then
    echo "ERRO: a API não ficou saudável (estado: ${status:-desconhecido})" >&2
    echo "--- últimas 60 linhas do log ---" >&2
    docker compose logs --tail=60 api >&2 || true
    exit 1
  fi
fi

echo
echo "=================================================================="
echo " VB Typer instalado"
echo "=================================================================="
echo " Interface:  $FRONTEND"
if [ "$MODE" = "public" ]; then
  echo " Acesso:     usuário \"$BASIC_USER\" · senha \"$BASIC_PASS\""
  echo "             (guarde agora: a senha não é exibida de novo)"
  echo " Certificado: o Caddy emite no primeiro acesso — se falhar, confira"
  echo "              as portas 80/443 e o DNS do domínio."
  echo
  echo " OBS: o Basic Auth é o portão temporário da interface; a API usa o token."
else
  echo " Acesso:     sem senha — a porta só escuta em 127.0.0.1."
  echo "             Para usar do celular ou de outra máquina, reinstale no"
  echo "             modo público (com domínio) ou exponha por VPN."
fi
echo
echo " API (clientes):  $BACKEND/api/v1/..."
echo " Token da API:    VB_TYPER_API_TOKEN no .env (chmod 600)"
echo " Desktop:         vb-typer-desktop --base-url $BACKEND"
echo "                  e copie o token para ~/.config/vb-typer/api-token"
echo
echo " Dados:  volume vb-typer-data (banco + áudios)"
echo " Parar:  docker compose down        (mantém os dados)"
if [ "$MODE" = "public" ]; then
  UPDATE_CMD="docker compose --profile public up -d --build"
else
  UPDATE_CMD="docker compose up -d --build"
fi
echo " Atualizar: git pull && $UPDATE_CMD"
echo "=================================================================="
