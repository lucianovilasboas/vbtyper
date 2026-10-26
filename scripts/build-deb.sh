#!/usr/bin/env bash
# =====================================================================
# Gera o pacote .deb do cliente desktop (instalação por duplo clique).
#
# O binário é o mesmo one-file do AppImage; o wrapper /usr/bin/vb-typer
# embute o domínio público apenas como padrão (as preferências do usuário
# vêm antes dele).
#
#     ./scripts/build-deb.sh [caminho-de-saída]
# =====================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
DESKTOP="$ROOT/desktop"
VERSION="$(cat "$ROOT/VERSION" 2>/dev/null || true)"
OUTPUT="${1:-$ROOT/dist/vb-typer_${VERSION}_amd64.deb}"

die() {
  printf 'Erro: %s\n' "$*" >&2
  exit 1
}

[[ -n "$VERSION" ]] || die "VERSION ausente; rode scripts/set-version.sh X.Y.Z."
command -v dpkg-deb >/dev/null 2>&1 || die "dpkg-deb não encontrado."

BUILD_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/vb-typer-deb.XXXXXX")"
trap 'rm -rf -- "$BUILD_ROOT"' EXIT
PKG="$BUILD_ROOT/pkg"
BINARY="$BUILD_ROOT/vb-typer-desktop"
OUTPUT_PATH="$(realpath -m "$OUTPUT")"

"$ROOT/scripts/build-binary.sh" "$BINARY"

install -Dm755 "$BINARY" "$PKG/opt/vb-typer/vb-typer-desktop"
install -Dm644 "$DESKTOP/assets/logo.png" \
  "$PKG/usr/share/icons/hicolor/256x256/apps/vb-typer.png"
install -Dm644 "$DESKTOP/assets/logo.png" "$PKG/opt/vb-typer/logo.png"

mkdir -p "$PKG/usr/bin"
cat > "$PKG/usr/bin/vb-typer" <<'EOF'
#!/bin/sh
# Wrapper do pacote: o binário real fica em /opt/vb-typer.
set -eu
exec /opt/vb-typer/vb-typer-desktop "$@"
EOF
chmod 0755 "$PKG/usr/bin/vb-typer"

mkdir -p "$PKG/usr/share/applications"
cat > "$PKG/usr/share/applications/vb-typer.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=VB Typer
Comment=Ditado por voz por atalho global (Ctrl+Super)
Exec=/usr/bin/vb-typer
Icon=vb-typer
Terminal=false
Categories=Utility;
StartupNotify=false
EOF
chmod 0644 "$PKG/usr/share/applications/vb-typer.desktop"

mkdir -p "$PKG/DEBIAN"
cat > "$PKG/DEBIAN/control" <<EOF
Package: vb-typer
Version: $VERSION
Architecture: amd64
Maintainer: Luciano Vilas Boas <lucianovilasboas@users.noreply.github.com>
Installed-Size: $(du -sk "$PKG" | cut -f1)
Depends: alsa-utils, libnotify-bin, python3-gi, python3-gi-cairo, gir1.2-gtk-3.0, gir1.2-ayatanaappindicator3-0.1, libglib2.0-bin, libx11-6, libxtst6
Recommends: xdg-utils
Section: utils
Priority: optional
Description: Ditado por voz por atalho global
 Cliente desktop do VB Typer: grava pelo atalho Ctrl+Super, transcreve pela
 API configurada e insere o texto no ponto do cursor. Inclui bandeja e
 indicador visual; o primeiro uso pede o endereço e o token da API.
EOF
chmod 0644 "$PKG/DEBIAN/control"

cat > "$PKG/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
exit 0
EOF
chmod 0755 "$PKG/DEBIAN/postinst"

mkdir -p "$(dirname "$OUTPUT_PATH")"
printf 'Gerando %s...\n' "$OUTPUT_PATH"
dpkg-deb --build --root-owner-group "$PKG" "$OUTPUT_PATH"
printf '\nPacote gerado: %s\n' "$OUTPUT_PATH"
