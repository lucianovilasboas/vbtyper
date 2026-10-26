#!/usr/bin/env bash
# =====================================================================
# Fonte única da versão do projeto.
#
# A tag do GitHub (`vX.Y.Z`) precisa bater com o conteúdo de VERSION; o
# workflow de release recusa publicar quando não bate.
#
#     ./scripts/set-version.sh 0.18.0
# =====================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
VERSION="${1:-}"

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "uso: $0 X.Y.Z" >&2
  exit 2
fi

printf '%s\n' "$VERSION" > "$ROOT/VERSION"
sed -i "s/^version = \"[^\"]*\"/version = \"$VERSION\"/" \
  "$ROOT/backend/pyproject.toml" \
  "$ROOT/desktop/pyproject.toml"
sed -i "s/^__version__ = \"[^\"]*\"/__version__ = \"$VERSION\"/" \
  "$ROOT/backend/src/vb_typer/__init__.py" \
  "$ROOT/desktop/src/vb_typer_desktop/__init__.py"

printf 'Versão %s aplicada em VERSION, pyprojects e __version__.\n' "$VERSION"
