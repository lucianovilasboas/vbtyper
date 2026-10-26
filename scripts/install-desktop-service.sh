#!/usr/bin/env bash
# Instala o cliente desktop como serviço systemd de usuário (sobe no login) e
# cria a entrada no menu de aplicativos.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESKTOP="$ROOT/desktop"
BIN="$DESKTOP/.venv/bin/vb-typer-desktop"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT="$UNIT_DIR/vb-typer-desktop.service"
RUNTIME="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
APPS_DIR="$DATA_DIR/applications"
ICON_DIR="$DATA_DIR/icons/hicolor/256x256/apps"
DISPLAY_VALUE="${DISPLAY:-:0}"
XAUTHORITY_VALUE="${XAUTHORITY:-$HOME/.Xauthority}"

if [[ ! -x "$BIN" ]]; then
  echo "Dependências ausentes. Rode antes: cd \"$DESKTOP\" && uv sync --extra dev" >&2
  exit 1
fi

if [[ ! -f "$DESKTOP/assets/logo.png" ]]; then
  echo "Ícone ausente. Gere com: cd \"$DESKTOP\" && uv run --with pillow python ../scripts/build-icons.py" >&2
  exit 1
fi

if ! systemctl --user is-active --quiet vb-typer-desktop.service 2>/dev/null \
   && pgrep -f "$BIN" >/dev/null 2>&1; then
  echo "Aviso: já existe um cliente rodando fora do systemd. Encerre-o (menu Sair" >&2
  echo "da bandeja) — senão o serviço vai apenas abrir a interface e sair." >&2
fi

mkdir -p "$UNIT_DIR" "$APPS_DIR" "$ICON_DIR"

sed -e "s|@DESKTOP_DIR@|$DESKTOP|g" \
    -e "s|@RUNTIME_DIR@|$RUNTIME|g" \
    -e "s|@DISPLAY@|$DISPLAY_VALUE|g" \
    -e "s|@XAUTHORITY@|$XAUTHORITY_VALUE|g" \
  "$ROOT/deploy/systemd/vb-typer-desktop.service" > "$UNIT"

install -m 0644 "$DESKTOP/assets/logo.png" "$ICON_DIR/vb-typer.png"

cat > "$APPS_DIR/vb-typer.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=VB Typer
Comment=Ditado por voz por atalho global (Ctrl+Super)
Exec=$BIN
Icon=vb-typer
Terminal=false
Categories=AudioVideo;Audio;
StartupNotify=false
EOF
chmod 0644 "$APPS_DIR/vb-typer.desktop"
if command -v update-desktop-database >/dev/null; then
  update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
fi

systemctl --user daemon-reload
systemctl --user enable --now vb-typer-desktop.service

echo
echo "Serviço instalado: $UNIT"
echo "Menu de aplicativos: $APPS_DIR/vb-typer.desktop"
echo "Ícone:         $ICON_DIR/vb-typer.png"
echo "Status:        systemctl --user status vb-typer-desktop"
echo "Logs:          journalctl --user -u vb-typer-desktop -f"
echo "Reiniciar:     systemctl --user restart vb-typer-desktop"
echo "Remover:       systemctl --user disable --now vb-typer-desktop \\"
echo "                 && rm \"$UNIT\" \"$APPS_DIR/vb-typer.desktop\" \\"
echo "                 && systemctl --user daemon-reload"
