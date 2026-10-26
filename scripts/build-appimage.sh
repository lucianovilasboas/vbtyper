#!/usr/bin/env bash
# Gera o AppImage do cliente desktop para Linux Mint/Cinnamon x86_64.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
DESKTOP="$ROOT/desktop"
VERSION="$(cat "$ROOT/VERSION" 2>/dev/null || sed -n 's/^version = "\([^"]*\)"/\1/p' "$DESKTOP/pyproject.toml" | head -n 1)"
ARCH="$(uname -m)"
OUTPUT="${1:-$ROOT/dist/VB-Typer-$VERSION-x86_64.AppImage}"
APPIMAGETOOL_BIN="${APPIMAGETOOL:-$(command -v appimagetool || true)}"

die() {
  printf 'Erro: %s\n' "$*" >&2
  exit 1
}

[[ -n "$VERSION" ]] || die "não foi possível ler a versão em VERSION."
[[ "$ARCH" == "x86_64" ]] || die "este build gera AppImage x86_64; arquitetura detectada: $ARCH."
[[ -n "$APPIMAGETOOL_BIN" && -x "$APPIMAGETOOL_BIN" ]] \
  || die "appimagetool não encontrado; instale-o ou defina APPIMAGETOOL=/caminho/appimagetool."

BUILD_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/vb-typer-appimage.XXXXXX")"
trap 'rm -rf -- "$BUILD_ROOT"' EXIT
APPDIR="$BUILD_ROOT/VB-Typer.AppDir"
BINARY="$BUILD_ROOT/vb-typer-desktop"
OUTPUT_PATH="$(realpath -m "$OUTPUT")"

mkdir -p \
  "$APPDIR/usr/bin" \
  "$APPDIR/usr/share/applications" \
  "$APPDIR/usr/share/icons/hicolor/256x256/apps"

"$ROOT/scripts/build-binary.sh" "$BINARY"

install -m 0755 "$ROOT/desktop/appimage/AppRun" "$APPDIR/AppRun"
install -m 0755 "$BINARY" "$APPDIR/usr/bin/vb-typer-desktop"
install -m 0644 "$DESKTOP/assets/logo.png" "$APPDIR/vb-typer.png"
install -m 0644 "$DESKTOP/assets/logo.png" \
  "$APPDIR/usr/share/icons/hicolor/256x256/apps/vb-typer.png"
sed "s/@VERSION@/$VERSION/g" \
  "$DESKTOP/appimage/vb-typer.desktop" > "$APPDIR/vb-typer.desktop"
install -m 0644 "$APPDIR/vb-typer.desktop" \
  "$APPDIR/usr/share/applications/vb-typer.desktop"
ln -s vb-typer.png "$APPDIR/.DirIcon"

mkdir -p "$(dirname "$OUTPUT_PATH")"
printf 'Gerando %s...\n' "$OUTPUT_PATH"
if [[ "$APPIMAGETOOL_BIN" == *.AppImage ]]; then
  VERSION="$VERSION" ARCH=x86_64 "$APPIMAGETOOL_BIN" \
    --appimage-extract-and-run "$APPDIR" "$OUTPUT_PATH"
else
  VERSION="$VERSION" ARCH=x86_64 "$APPIMAGETOOL_BIN" "$APPDIR" "$OUTPUT_PATH"
fi
chmod 0755 "$OUTPUT_PATH"
printf '\nAppImage gerado: %s\n' "$OUTPUT_PATH"
