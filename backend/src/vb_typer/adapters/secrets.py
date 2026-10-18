"""Acesso ao cofre do sistema.

No Linux usa Secret Service (GNOME Keyring/KWallet), no macOS o Keychain e no
Windows o Credential Locker. O serviço/usuário são os mesmos do app 1.x para que
a chave já configurada continue valendo.
"""

from __future__ import annotations

import os

from vb_typer.core.config import AppSettings


class SecretsAdapter:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def get_api_key(self) -> str:
        """``OPENAI_API_KEY`` tem precedência sobre o cofre (útil em CI)."""
        env_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if env_key:
            return env_key
        try:
            import keyring

            return (
                keyring.get_password(self.settings.keyring_service, self.settings.keyring_username)
                or ""
            )
        except Exception:
            return ""

    def has_api_key(self) -> bool:
        return bool(self.get_api_key())

    def store_api_key(self, key: str) -> None:
        value = (key or "").strip()
        if not value:
            raise ValueError("A chave não pode ficar em branco.")
        import keyring

        keyring.set_password(self.settings.keyring_service, self.settings.keyring_username, value)
        stored = keyring.get_password(self.settings.keyring_service, self.settings.keyring_username)
        if stored != value:
            raise RuntimeError("O cofre do sistema não confirmou a gravação da chave.")
