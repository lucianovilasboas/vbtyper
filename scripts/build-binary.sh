#!/usr/bin/env bash
# =====================================================================
# Gera o executável one-file do cliente desktop (PyInstaller).
#
# Usado pelo AppImage e pelo .deb para os dois levarem exatamente o mesmo
# binário. Saída padrão: dist/vb-typer-desktop
#
#     ./scripts/build-binary.sh [caminho-de-saída]
# =====================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
DESKTOP="$ROOT/desktop"
OUTPUT="${1:-$ROOT/dist/vb-typer-desktop}"
OUTPUT_PATH="$(realpath -m "$OUTPUT")"
DIST_DIR="$(dirname "$OUTPUT_PATH")"
NAME="$(basename "$OUTPUT_PATH")"

die() {
  printf 'Erro: %s\n' "$*" >&2
  exit 1
}

VERSION="$(cat "$ROOT/VERSION" 2>/dev/null || true)"
[[ -n "$VERSION" ]] || die "VERSION ausente; rode scripts/set-version.sh X.Y.Z."
command -v uv >/dev/null 2>&1 || die "uv não encontrado; instale uv para preparar o build."

BUILD_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/vb-typer-binary.XXXXXX")"
trap 'rm -rf -- "$BUILD_ROOT"' EXIT

# Caches de teste nunca podem entrar no pacote.
find "$DESKTOP/tray" -name "__pycache__" -type d -prune -exec rm -rf {} +
mkdir -p "$DIST_DIR" "$BUILD_ROOT/work" "$BUILD_ROOT/spec"

printf 'Empacotando o cliente Python %s...\n' "$VERSION"
uv run --project "$DESKTOP" --extra build pyinstaller \
  --noconfirm \
  --clean \
  --onefile \
  --name "$NAME" \
  --paths "$DESKTOP/src" \
  --add-data "$DESKTOP/tray:tray" \
  --add-data "$DESKTOP/assets:assets" \
  --distpath "$DIST_DIR" \
  --workpath "$BUILD_ROOT/work" \
  --specpath "$BUILD_ROOT/spec" \
  "$DESKTOP/src/vb_typer_desktop/__main__.py"

chmod 0755 "$OUTPUT_PATH"
printf 'Binário gerado: %s\n' "$OUTPUT_PATH"
