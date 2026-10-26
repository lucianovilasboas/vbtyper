"""Conexão com a API: URL, token, primeiro uso, integração e autostart.

O token da API é um segredo local: nunca é embutido no AppImage publicado nem
passado por argumentos de linha de comando. O primeiro uso pergunta a URL e o
token, valida e grava o token em ``~/.config/vb-typer/api-token`` (0600).
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlparse

import httpx

from vb_typer_desktop import preferences
from vb_typer_desktop.api import DEFAULT_BASE_URL, token_file
from vb_typer_desktop.tray import gtklib_available, resource_path

SYSTEM_PYTHON = "/usr/bin/python3"
SETUP_HELPER = "tray/setup.py"
AUTOSTART_NAME = "vb-typer.desktop"
MENU_NAME = "vb-typer.desktop"
ICON_NAME = "vb-typer.png"
STABLE_APPIMAGE = "VB-Typer.AppImage"
PROBE_TIMEOUT_S = 8.0
# Endereço público embutido nos pacotes. Não é um override: fica abaixo das
# preferências no diálogo, para o usuário poder apontar para outro servidor.
PACKAGED_DEFAULT_URL = "https://vbtyper.lucianovilasboas.com.br"


@dataclass(frozen=True)
class SetupResult:
    """O que o diálogo devolveu; ``token`` vazio significa "manter o atual"."""

    url: str
    token: str
    autostart: bool


def _config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def normalize_url(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if "://" not in text:
        host = text.split("/", 1)[0].split(":", 1)[0].lower()
        scheme = "http" if host in {"localhost", "127.0.0.1", "::1"} else "https"
        text = f"{scheme}://{text}"
    return text.rstrip("/")


def default_base_url() -> str:
    """Padrão do pacote (domínio) ou da API local no código-fonte."""
    if os.environ.get("APPIMAGE") or getattr(sys, "frozen", False):
        return PACKAGED_DEFAULT_URL
    return DEFAULT_BASE_URL


def resolve_base_url(cli_value: str | None, current: preferences.Preferences) -> str:
    """Precedência: flag > ambiente > preferências > padrão do pacote."""
    if cli_value:
        return normalize_url(cli_value)
    env_value = os.environ.get("VB_TYPER_API_BASE_URL", "").strip()
    if env_value:
        return normalize_url(env_value)
    if current.base_url:
        return normalize_url(current.base_url)
    return default_base_url()


def stored_token() -> str | None:
    """Token gravado em disco (ignora a variável de ambiente)."""
    try:
        value = token_file().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def has_token() -> bool:
    return bool(os.environ.get("VB_TYPER_API_TOKEN", "").strip() or stored_token())


def save_token(token: str) -> Path:
    """Grava o token com 0600, sem deixar cópia temporária legível."""
    value = (token or "").strip()
    if not value:
        raise ValueError("O token não pode ficar em branco.")
    target = token_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        target.parent.chmod(0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".api-token-", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        with contextlib.suppress(OSError):
            Path(temporary).unlink()
    return target


def save_connection(url: str, token: str) -> Path:
    """Grava a URL em ``desktop.json`` e, quando informado, o token.

    ``token`` vazio mantém o token atual (reconfiguração sem redigitar).
    """
    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    if not normalized or not parsed.netloc:
        raise ValueError("Informe um endereço válido, como https://vbtyper.exemplo.com.")
    target = save_token(token) if token.strip() else token_file()
    current = preferences.load()
    preferences.save(replace(current, base_url=normalized))
    return target


def probe(url: str, token: str, timeout: float = PROBE_TIMEOUT_S) -> tuple[bool, str]:
    """Testa URL + token sem revelar o token em mensagens."""
    normalized = normalize_url(url)
    if not normalized:
        return False, "Informe o endereço do servidor."
    value = (token or "").strip() or (stored_token() or "")
    if not value:
        return False, "Informe o token de acesso."
    try:
        response = httpx.get(
            f"{normalized}/api/v1/settings",
            headers={"Authorization": f"Bearer {value}"},
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        return False, f"Não foi possível conectar: {exc}"
    if response.status_code == 200:
        return True, "Conexão ok."
    if response.status_code == 401:
        return False, "Token recusado. Confira o token e tente de novo."
    return False, f"A API respondeu HTTP {response.status_code}."


def autostart_file() -> Path:
    return _config_home() / "autostart" / AUTOSTART_NAME


def autostart_installed() -> bool:
    return autostart_file().is_file()


def _exec_value(path: str) -> str:
    return f'"{path}"' if " " in path else path


def install_autostart(exec_path: str) -> Path:
    """Escreve a entrada XDG que inicia o cliente no login."""
    target = autostart_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=VB Typer\n"
        "Comment=Ditado por voz por atalho global (Ctrl+Super)\n"
        f"Exec={_exec_value(exec_path)}\n"
        "Icon=vb-typer\n"
        "Terminal=false\n"
        "StartupNotify=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        "X-GNOME-Autostart-Delay=3\n"
    )
    target.write_text(content, encoding="utf-8")
    with contextlib.suppress(OSError):
        target.chmod(0o644)
    return target


def remove_autostart() -> None:
    with contextlib.suppress(OSError):
        autostart_file().unlink()


def stable_appimage_path() -> Path:
    return Path.home() / ".local" / "bin" / STABLE_APPIMAGE


def install_appimage(source: Path | None = None) -> Path | None:
    """Copia o AppImage em execução para um caminho estável (menu/autostart)."""
    origin = source or (Path(os.environ["APPIMAGE"]) if os.environ.get("APPIMAGE") else None)
    if origin is None:
        return None
    origin = Path(origin)
    target = stable_appimage_path()
    if origin.resolve() == target.resolve():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".VB-Typer-", dir=target.parent)
    os.close(descriptor)
    try:
        shutil.copy2(origin, temporary)
        os.chmod(temporary, 0o755)
        os.replace(temporary, target)
    finally:
        with contextlib.suppress(OSError):
            Path(temporary).unlink()
    return target


def write_menu_entry(exec_path: str) -> Path:
    """Cria o item de menu do usuário, usado pela integração do AppImage."""
    applications = _data_home() / "applications"
    applications.mkdir(parents=True, exist_ok=True)
    target = applications / MENU_NAME
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=VB Typer\n"
        "Comment=Ditado por voz por atalho global (Ctrl+Super)\n"
        f"Exec={_exec_value(exec_path)}\n"
        "Icon=vb-typer\n"
        "Terminal=false\n"
        "Categories=Utility;\n"
        "StartupNotify=false\n"
    )
    target.write_text(content, encoding="utf-8")
    with contextlib.suppress(OSError):
        target.chmod(0o644)
        icons = _data_home() / "icons" / "hicolor" / "256x256" / "apps"
        icons.mkdir(parents=True, exist_ok=True)
        shutil.copy2(resource_path("assets/logo.png"), icons / ICON_NAME)
    if shutil.which("update-desktop-database"):
        with contextlib.suppress(OSError):
            subprocess.run(
                ["update-desktop-database", str(applications)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
    return target


def install_integration() -> Path:
    """Instala o executável atual no caminho estável e liga o autostart.

    No .deb, ``/usr/bin/vb-typer`` já existe e o menu é do sistema: só o
    autostart do usuário é escrito. No AppImage, copia para ``~/.local/bin``.
    """
    packaged = Path("/usr/bin/vb-typer")
    if packaged.is_file():
        install_autostart(str(packaged))
        return packaged

    stable = install_appimage()
    if stable is not None:
        write_menu_entry(str(stable))
        install_autostart(str(stable))
        return stable

    executable = str(Path(sys.argv[0]).resolve())
    install_autostart(executable)
    return Path(executable)


def run_setup_dialog(
    current_url: str,
    *,
    autostart: bool = False,
    token_saved: bool = False,
) -> SetupResult | None:
    """Abre o diálogo GTK e devolve o que o usuário preencheu.

    O token não passa por argumentos: o helper grava um JSON temporário 0600,
    que o chamador lê e apaga.
    """
    if not gtklib_available():
        print("GTK3 não encontrado; instale python3-gi para configurar a conexão.", file=sys.stderr)
        return None
    helper = resource_path(SETUP_HELPER)
    if not helper.is_file():
        print(f"Diálogo de configuração ausente: {helper}", file=sys.stderr)
        return None

    descriptor, result_name = tempfile.mkstemp(prefix="vb-typer-setup-", suffix=".json")
    os.close(descriptor)
    result_path = Path(result_name)
    command = [
        SYSTEM_PYTHON,
        str(helper),
        "--url",
        current_url,
        "--result",
        str(result_path),
    ]
    if autostart:
        command.append("--autostart")
    if token_saved:
        command.append("--token-saved")
    try:
        completed = subprocess.run(command, check=False)
        if completed.returncode != 0:
            return None
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        url = normalize_url(str(payload.get("url") or ""))
        token = str(payload.get("token") or "").strip()
        if not url or (not token and not (token_saved or has_token())):
            return None
        return SetupResult(url=url, token=token, autostart=bool(payload.get("autostart")))
    finally:
        with contextlib.suppress(OSError):
            result_path.unlink()


def configure_interactively(
    current_url: str, current: preferences.Preferences
) -> SetupResult | None:
    """Diálogo + gravação + integração; ``None`` quando o usuário cancela."""
    result = run_setup_dialog(
        current_url,
        autostart=autostart_installed(),
        token_saved=has_token(),
    )
    if result is None:
        return None
    save_connection(result.url, result.token)
    if result.autostart:
        install_integration()
    else:
        remove_autostart()
    return result
