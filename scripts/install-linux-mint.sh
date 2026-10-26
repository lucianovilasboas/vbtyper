#!/usr/bin/env bash
# Instala o cliente desktop do VB Typer 2.0 no Linux Mint Cinnamon.
set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
INSTALL_DIR="$DATA_HOME/vb-typer-app"
INSTALL_MARKER="$INSTALL_DIR/.vb-typer-install"
UNIT_DIR="$CONFIG_HOME/systemd/user"
APPS_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/256x256/apps"
LOCAL_BIN="$HOME/.local/bin"
TOKEN_FILE="$CONFIG_HOME/vb-typer/api-token"
ZEROTIER_URL="http://10.147.20.2:8766"
TAILSCALE_URL="https://xps.tail5ae70d.ts.net:8444"
DOMAIN_URL="https://vbtyper.lucianovilasboas.com.br"
BACKEND_URL="$DOMAIN_URL"
UV_BIN=""
UNINSTALL=0

usage() {
  cat <<'EOF'
Uso:
  scripts/install-linux-mint.sh [--domain | --zerotier | --tailscale | --backend-url URL]
  scripts/install-linux-mint.sh --uninstall

Instala o cliente desktop para o usuário atual e configura a URL do servidor.
O padrão é https://vbtyper.lucianovilasboas.com.br.

Opções:
  --domain         usar https://vbtyper.lucianovilasboas.com.br (padrão)
  --zerotier       usar http://10.147.20.2:8766
  --tailscale      usar https://xps.tail5ae70d.ts.net:8444
  --backend-url URL usar outro endereço http(s)://host:porta
  --uninstall      remover cliente, serviço, atalho e ícone
  -h, --help       mostrar esta ajuda
EOF
}

die() {
  printf 'Erro: %s\n' "$*" >&2
  exit 1
}

parse_arguments() {
  while (($#)); do
    case "$1" in
      --domain)
        BACKEND_URL="$DOMAIN_URL"
        shift
        ;;
      --zerotier)
        BACKEND_URL="$ZEROTIER_URL"
        shift
        ;;
      --tailscale)
        BACKEND_URL="$TAILSCALE_URL"
        shift
        ;;
      --backend-url)
        (($# >= 2)) || die "--backend-url precisa de uma URL."
        BACKEND_URL="${2%/}"
        shift 2
        ;;
      --uninstall)
        UNINSTALL=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        usage >&2
        exit 2
        ;;
    esac
  done
}

validate_backend_url() {
  if ! python3 - "$BACKEND_URL" <<'PY'
import re
from urllib.parse import urlsplit
import sys

try:
    value = sys.argv[1]
    parsed = urlsplit(value)
    valid = (
        parsed.scheme in {"http", "https"}
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
        and not parsed.path
        and not parsed.query
        and not parsed.fragment
        and re.fullmatch(r"https?://[A-Za-z0-9.\[\]:-]+", value)
        and (parsed.port is None or 1 <= parsed.port <= 65535)
    )
except ValueError:
    valid = False

raise SystemExit(0 if valid else 1)
PY
  then
    die "URL inválida; use http(s)://host ou http(s)://host:porta, sem caminho."
  fi
}

check_platform() {
  [[ $EUID -ne 0 ]] || die "execute como usuário normal, sem sudo."
  [[ -r /etc/os-release ]] || die "não foi possível identificar a distribuição Linux."
  # shellcheck disable=SC1091
  source /etc/os-release
  [[ "${ID:-}" == "linuxmint" ]] || die "este instalador foi preparado para Linux Mint."

  [[ -n "${DISPLAY:-}" ]] \
    || die "abra um terminal na sessão gráfica do Cinnamon e tente novamente."
  [[ "${XDG_SESSION_TYPE:-x11}" != "wayland" ]] || die "o cliente desktop requer uma sessão X11."
  command -v systemctl >/dev/null 2>&1 || die "systemd não foi encontrado."
  systemctl --user show-environment >/dev/null 2>&1 \
    || die "a sessão do systemd do usuário não está disponível;"\
      " entre no Cinnamon e tente novamente."

  python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
    || die "o VB Typer requer Python 3.11 ou mais recente."
}

uninstall() {
  if [[ -e "$INSTALL_DIR" && ! -f "$INSTALL_MARKER" ]]; then
    die "o diretório existe e não pertence ao instalador; arquivos preservados: $INSTALL_DIR"
  fi

  systemctl --user disable --now vb-typer-desktop.service >/dev/null 2>&1 || true
  rm -f \
    "$UNIT_DIR/vb-typer-desktop.service" \
    "$APPS_DIR/vb-typer.desktop" \
    "$ICON_DIR/vb-typer.png"
  systemctl --user daemon-reload >/dev/null 2>&1 || true
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
  fi

  if [[ -d "$INSTALL_DIR" ]]; then
    case "$INSTALL_DIR" in
      */vb-typer-app) rm -rf -- "$INSTALL_DIR" ;;
      *) die "caminho de instalação inesperado; arquivos preservados: $INSTALL_DIR" ;;
    esac
  fi

  printf 'Cliente removido. Token e preferências foram preservados em %s/vb-typer.\n' \
    "$CONFIG_HOME"
}

install_system_dependencies() {
  local -a packages=(
    alsa-utils
    ca-certificates
    curl
    gir1.2-ayatanaappindicator3-0.1
    gir1.2-gtk-3.0
    libasound2-plugins
    libnotify-bin
    python3
    python3-gi
    xdg-utils
  )
  local -a missing=()
  local package

  for package in "${packages[@]}"; do
    if ! dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed'; then
      missing+=("$package")
    fi
  done

  if ((${#missing[@]} == 0)); then
    printf 'Dependências do sistema: já instaladas.\n'
    return
  fi

  command -v apt-get >/dev/null 2>&1 || die "apt-get não foi encontrado."
  command -v sudo >/dev/null 2>&1 || die "sudo é necessário para instalar: ${missing[*]}"
  printf 'Instalando dependências do sistema: %s\n' "${missing[*]}"
  sudo apt-get update
  sudo apt-get install -y "${missing[@]}"
}

find_uv() {
  if command -v uv >/dev/null 2>&1; then
    UV_BIN="$(command -v uv)"
  elif [[ -x "$LOCAL_BIN/uv" ]]; then
    UV_BIN="$LOCAL_BIN/uv"
  else
    mkdir -p "$LOCAL_BIN"
    printf 'Instalando uv em %s...\n' "$LOCAL_BIN"
    curl --proto '=https' --tlsv1.2 -LsSf https://astral.sh/uv/install.sh \
      | env UV_INSTALL_DIR="$LOCAL_BIN" UV_NO_MODIFY_PATH=1 sh
    [[ -x "$LOCAL_BIN/uv" ]] || die "o instalador do uv terminou sem criar $LOCAL_BIN/uv"
    UV_BIN="$LOCAL_BIN/uv"
  fi
}

copy_project() {
  [[ "$SOURCE_ROOT" == "$INSTALL_DIR" ]] && return
  if [[ -L "$INSTALL_DIR" ]]; then
    die "o caminho de instalação é um link simbólico; arquivos preservados: $INSTALL_DIR"
  fi
  if [[ -e "$INSTALL_DIR" && ! -f "$INSTALL_MARKER" ]]; then
    die "o diretório já existe e não pertence ao instalador: $INSTALL_DIR"
  fi

  printf 'Copiando o projeto para %s...\n' "$INSTALL_DIR"
  mkdir -p "$INSTALL_DIR"
  tar \
    --exclude-vcs \
    --exclude='./.venv' --exclude='*/.venv' \
    --exclude='./.env' --exclude='*/.env' \
    --exclude='./.pytest_cache' --exclude='*/.pytest_cache' \
    --exclude='./.ruff_cache' --exclude='*/.ruff_cache' \
    --exclude='__pycache__' --exclude='*/__pycache__' \
    -C "$SOURCE_ROOT" -cf - . | tar -C "$INSTALL_DIR" -xf -
  touch "$INSTALL_MARKER"
}

save_api_token() {
  local token="$1"
  local token_dir token_tmp
  token_dir="$(dirname "$TOKEN_FILE")"
  mkdir -p "$token_dir"
  chmod 700 "$token_dir"
  token_tmp="$(mktemp "$token_dir/.api-token.XXXXXX")"
  printf '%s\n' "$token" > "$token_tmp"
  chmod 600 "$token_tmp"
  mv -f -- "$token_tmp" "$TOKEN_FILE"
}

configure_api_token() {
  local token="" answer
  if [[ -n "${VB_TYPER_API_TOKEN:-}" ]]; then
    token="$VB_TYPER_API_TOKEN"
  elif [[ -s "$TOKEN_FILE" ]]; then
    if [[ -t 0 ]]; then
      read -r -p 'Token local encontrado. Substituí-lo? [s/N] ' answer
      case "$answer" in
        s|S|sim|SIM) ;;
        *)
          chmod 600 "$TOKEN_FILE"
          printf 'Token existente será mantido.\n'
          return
          ;;
      esac
    else
      chmod 600 "$TOKEN_FILE"
      printf 'Token existente será mantido.\n'
      return
    fi
  fi

  if [[ -z "$token" ]]; then
    [[ -t 0 ]] || die "token ausente; rode o instalador em um terminal interativo."
    read -r -s -p 'Token Bearer do servidor VB Typer: ' token
    printf '\n'
  fi
  [[ -n "$token" ]] || die "token vazio; instalação cancelada."
  [[ ! "$token" =~ [[:space:]] ]] || die "token inválido: não pode conter espaços."

  save_api_token "$token"
  unset token
  printf 'Token salvo com permissão 0600 em %s.\n' "$TOKEN_FILE"
}

install_app() {
  check_platform
  validate_backend_url
  install_system_dependencies
  find_uv
  copy_project

  printf 'Preparando ambiente do cliente desktop...\n'
  "$UV_BIN" sync --project "$INSTALL_DIR/desktop" --no-dev
  configure_api_token

  export VB_TYPER_API_BASE_URL="$BACKEND_URL"
  "$INSTALL_DIR/scripts/install-desktop-service.sh"
  systemctl --user restart vb-typer-desktop.service

  printf '\nVerificando conexão com o servidor...\n'
  if "$INSTALL_DIR/desktop/.venv/bin/vb-typer-desktop" \
      --self-test --base-url "$BACKEND_URL"; then
    printf 'Cliente conectado ao servidor.\n'
  else
    printf 'Cliente instalado; confira o ZeroTier/Tailscale, a URL e o token.\n' >&2
  fi

  cat <<EOF

Cliente VB Typer instalado no Linux Mint Cinnamon.

- Servidor: $BACKEND_URL
- Abra “VB Typer” pelo menu de aplicativos.
- Atalho para ditar: segure Ctrl+Super e solte para transcrever.
- O serviço inicia automaticamente no login.
- Estado: systemctl --user status vb-typer-desktop
- Logs: journalctl --user -u vb-typer-desktop -f
- Remover: $INSTALL_DIR/scripts/install-linux-mint.sh --uninstall

O áudio segue pela rede VPN até o backend; o texto é inserido nesta máquina.
EOF
}

parse_arguments "$@"
if ((UNINSTALL)); then
  uninstall
else
  install_app
fi
