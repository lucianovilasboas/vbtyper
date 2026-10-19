"""Preferências do cliente desktop, em ``~/.config/vb-typer/desktop.json``."""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from vb_typer_desktop.geometry import ANCHORS, POSITIONS

NOTICE_MODES = ("indicator", "balloons", "both", "none")
DEFAULTS = {
    "notices": "indicator",
    "anchor": "window",
    "position": "bottom-center",
    "sound": False,
    "size": 40,
}
MIN_SIZE, MAX_SIZE = 24, 96


def preference_file() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "vb-typer" / "desktop.json"


@dataclass(frozen=True)
class Preferences:
    """Como o ditado avisa o que está acontecendo.

    ``notices``:
      * ``indicator`` — indicador visual na tela; balão só para erro (padrão);
      * ``balloons``  — comportamento antigo: balão do sistema para tudo;
      * ``both``      — indicador e balões de rotina;
      * ``none``      — nada na tela.
    """

    notices: str = DEFAULTS["notices"]
    anchor: str = DEFAULTS["anchor"]
    position: str = DEFAULTS["position"]
    sound: bool = DEFAULTS["sound"]
    size: int = DEFAULTS["size"]

    @property
    def shows_indicator(self) -> bool:
        return self.notices in ("indicator", "both")

    @property
    def shows_routine_balloons(self) -> bool:
        return self.notices in ("balloons", "both")

    @property
    def shows_error_balloons(self) -> bool:
        return self.notices != "none"


def _pick(value, allowed: tuple[str, ...], default: str) -> str:
    return value if value in allowed else default


def from_mapping(values) -> Preferences:
    """Lê preferências de um dicionário, ignorando valores inválidos."""
    if not isinstance(values, dict):
        return Preferences()
    size = values.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or not MIN_SIZE <= size <= MAX_SIZE:
        size = DEFAULTS["size"]
    sound = values.get("sound")
    return Preferences(
        notices=_pick(values.get("notices"), NOTICE_MODES, DEFAULTS["notices"]),
        anchor=_pick(values.get("anchor"), ANCHORS, DEFAULTS["anchor"]),
        position=_pick(values.get("position"), POSITIONS, DEFAULTS["position"]),
        sound=sound if isinstance(sound, bool) else DEFAULTS["sound"],
        size=size,
    )


def load(path: Path | None = None) -> Preferences:
    """Lê as preferências; arquivo ausente ou inválido cai nos padrões."""
    target = path or preference_file()
    try:
        return from_mapping(json.loads(target.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return Preferences()


def save(preferences: Preferences, path: Path | None = None) -> Path:
    """Grava as preferências (usado para criar o arquivo e poder editá-lo)."""
    target = path or preference_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(asdict(preferences), ensure_ascii=False, indent=2) + "\n"
    target.write_text(body, encoding="utf-8")
    with contextlib.suppress(OSError):
        target.chmod(0o600)
    return target
