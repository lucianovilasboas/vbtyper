"""Cliente HTTP da API REST local do VB Typer."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8765"
TOKEN_ENV_VAR = "VB_TYPER_API_TOKEN"
TERMINAL_STATUSES = frozenset({"succeeded", "failed", "canceled"})


class ApiError(RuntimeError):
    """Falha de comunicação com a API ou erro de domínio devolvido por ela."""


def token_file() -> Path:
    """Caminho do token gravado pelo backend (arquivo 0600)."""
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "vb-typer" / "api-token"


def load_token() -> str | None:
    """Token da API; a variável de ambiente tem precedência sobre o arquivo."""
    override = os.environ.get(TOKEN_ENV_VAR, "").strip()
    if override:
        return override
    try:
        value = token_file().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


@dataclass(frozen=True)
class Job:
    """Estado de um job de transcrição segundo a API."""

    id: str
    status: str
    error: str | None = None
    transcription_id: int | None = None
    text: str = ""

    @property
    def finished(self) -> bool:
        return self.status in TERMINAL_STATUSES


def parse_job(payload: dict) -> Job:
    result = payload.get("result") or {}
    return Job(
        id=str(payload.get("id", "")),
        status=str(payload.get("status", "")),
        error=payload.get("error"),
        transcription_id=payload.get("transcription_id"),
        text=str(result.get("text") or ""),
    )


def error_message(response: httpx.Response) -> str:
    """Extrai a mensagem do envelope de erro da API, quando existir."""
    try:
        payload = response.json()
    except ValueError:
        return f"A API respondeu HTTP {response.status_code}."
    if isinstance(payload, dict):
        envelope = payload.get("error")
        if isinstance(envelope, dict) and envelope.get("message"):
            return str(envelope["message"])
        if payload.get("detail"):
            return str(payload["detail"])
    return f"A API respondeu HTTP {response.status_code}."


class ApiClient:
    """Acesso à API local; o token nunca é logado nem devolvido ao chamador."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        token: str | None = None,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = load_token() if token is None else token
        self._client = client or httpx.Client(timeout=timeout)

    @property
    def client(self) -> httpx.Client:
        return self._client

    def close(self) -> None:
        self._client.close()

    def _headers(self) -> dict[str, str]:
        if not self._token:
            return {}
        return {"Authorization": f"Bearer {self._token}"}

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = f"{self.base_url}{path}"
        try:
            response = self._client.request(method, url, headers=self._headers(), **kwargs)
        except httpx.HTTPError as exc:
            raise ApiError(f"Não foi possível falar com a API do VB Typer: {exc}") from exc
        if response.status_code >= 400:
            raise ApiError(error_message(response))
        return response

    def ready(self) -> dict:
        """Estado de prontidão; nunca devolve segredos."""
        return self._request("GET", "/api/v1/ready").json()

    def settings(self) -> dict:
        return self._request("GET", "/api/v1/settings").json()

    def create_job(
        self,
        data: bytes,
        filename: str,
        content_type: str,
        model: str | None = None,
        language: str | None = None,
        mode: str | None = None,
    ) -> Job:
        """Envia o áudio e recebe ``202`` com o job aceito."""
        fields = {
            key: value
            for key, value in (("model", model), ("language", language), ("mode", mode))
            if value
        }
        response = self._request(
            "POST",
            "/api/v1/transcription-jobs",
            files={"file": (filename, data, content_type)},
            data=fields,
        )
        return parse_job(response.json())

    def get_job(self, job_id: str) -> Job:
        return parse_job(self._request("GET", f"/api/v1/transcription-jobs/{job_id}").json())

    def cancel_job(self, job_id: str) -> Job:
        """Cancela o job; cobrança já enviada ao provedor não é estornada."""
        return parse_job(self._request("DELETE", f"/api/v1/transcription-jobs/{job_id}").json())

    def mark_inserted(
        self, transcription_id: int, inserted: bool, insert_ms: int | None = None
    ) -> None:
        payload: dict = {"inserted": inserted}
        if insert_ms is not None:
            payload["insert_ms"] = insert_ms
        self._request("PATCH", f"/api/v1/transcriptions/{transcription_id}", json=payload)

    def current_options(self) -> tuple[str, str, str]:
        """Modelo, idioma e modo escolhidos na interface.

        A falha nunca impede o ditado: sem resposta, o backend decide pelos
        padrões dele (literal entre eles).
        """
        try:
            payload = self.settings()
        except ApiError:
            return "", "", ""
        return (
            str(payload.get("model") or ""),
            str(payload.get("language") or ""),
            str(payload.get("mode") or ""),
        )
