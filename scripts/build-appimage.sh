#!/usr/bin/env bash
# Gera o AppImage do cliente desktop para Linux Mint/Cinnamon x86_64.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
DESKTOP="$ROOT/desktop"
VERSION="$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$DESKTOP/pyproject.toml" | head -n 1)"
ARCH="$(uname -m)"
OUTPUT="${1:-$ROOT/dist/VB-Typer-$VERSION-x86_64.AppImage}"
APPIMAGETOOL_BIN="${APPIMAGETOOL:-$(command -v appimagetool || true)}"

die() {
  printf 'Erro: %s\n' "$*" >&2
  exit 1
}

[[ -n "$VERSION" ]] || die "não foi possível ler a versão em desktop/pyproject.toml."
[[ "$ARCH" == "x86_64" ]] || die "este build gera AppImage x86_64; arquitetura detectada: $ARCH."
[[ -n "$APPIMAGETOOL_BIN" && -x "$APPIMAGETOOL_BIN" ]] \
  || die "appimagetool não encontrado; instale-o ou defina APPIMAGETOOL=/caminho/appimagetool."
command -v uv >/dev/null 2>&1 || die "uv não encontrado; instale uv para preparar o build Python."

BUILD_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/vb-typer-appimage.XXXXXX")"
trap 'rm -rf -- "$BUILD_ROOT"' EXIT
APPDIR="$BUILD_ROOT/VB-Typer.AppDir"
PYINSTALLER_DIR="$BUILD_ROOT/pyinstaller"
OUTPUT_PATH="$(realpath -m "$OUTPUT")"

mkdir -p \
  "$APPDIR/usr/bin" \
  "$APPDIR/usr/share/applications" \
  "$APPDIR/usr/share/icons/hicolor/256x256/apps" \
  "$PYINSTALLER_DIR/dist" \
  "$PYINSTALLER_DIR/work" \
  "$PYINSTALLER_DIR/spec"

printf 'Empacotando o cliente Python %s...\n' "$VERSION"
uv run --project "$DESKTOP" --extra build pyinstaller \
  --noconfirm \
  --clean \
  --onefile \
  --name vb-typer-desktop \
  --paths "$DESKTOP/src" \
  --add-data "$DESKTOP/tray:tray" \
  --add-data "$DESKTOP/assets:assets" \
  --distpath "$PYINSTALLER_DIR/dist" \
  --workpath "$PYINSTALLER_DIR/work" \
  --specpath "$PYINSTALLER_DIR/spec" \
  "$DESKTOP/src/vb_typer_desktop/__main__.py"

install -m 0755 "$ROOT/desktop/appimage/AppRun" "$APPDIR/AppRun"
install -m 0755 \
  "$PYINSTALLER_DIR/dist/vb-typer-desktop" \
  "$APPDIR/usr/bin/vb-typer-desktop"
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
