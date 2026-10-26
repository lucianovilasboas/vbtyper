#!/usr/bin/env bash
# Instala e habilita o backend como serviço systemd de usuário.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT="$UNIT_DIR/vb-typer-api.service"
RUNTIME="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
PORT="${VB_TYPER_PORT:-8765}"

if [[ ! -x "$BACKEND/.venv/bin/vb-typer-api" ]]; then
  echo "Dependências ausentes. Rode antes: cd \"$BACKEND\" && uv sync --extra dev" >&2
  exit 1
fi

if command -v ss >/dev/null && ss -ltn 2>/dev/null | grep -q ":${PORT} "; then
  echo "Aviso: a porta ${PORT} já está em uso. Encerre a instância manual para o serviço assumir." >&2
fi

mkdir -p "$UNIT_DIR"
sed -e "s|@BACKEND_DIR@|$BACKEND|g" -e "s|@RUNTIME_DIR@|$RUNTIME|g" \
  "$ROOT/deploy/systemd/vb-typer-api.service" > "$UNIT"

systemctl --user daemon-reload
systemctl --user enable --now vb-typer-api.service

echo
echo "Serviço instalado: $UNIT"
echo "API:    http://127.0.0.1:${PORT}"
echo "Status: systemctl --user status vb-typer-api"
echo "Logs:   journalctl --user -u vb-typer-api -f"
echo "Remover: systemctl --user disable --now vb-typer-api && rm \"$UNIT\" && systemctl --user daemon-reload"
