"""Adaptador da API OpenAI (transcrição e verificação de credencial)."""

from __future__ import annotations

import json

import httpx

from vb_typer.domain.errors import ApiKeyMissingError, ProviderError


class OpenAIAdapter:
    def __init__(self, base_url: str, timeout_s: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_s)

    @staticmethod
    def _detail(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError):
            return response.text[:200].strip()
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or "").strip()[:300]
            if isinstance(error, str):
                return error[:300]
        return ""

    async def transcribe(
        self,
        *,
        audio: bytes,
        filename: str,
        content_type: str,
        model: str,
        language: str,
        api_key: str,
    ) -> dict:
        if not api_key:
            raise ApiKeyMissingError("Chave OpenAI ausente. Configure-a no cofre do sistema.")
        files = {"file": (filename or "recording.wav", audio, content_type or "audio/wav")}
        data = {"model": model, "language": language}
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            async with self._client() as client:
                response = await client.post(
                    "/audio/transcriptions", files=files, data=data, headers=headers
                )
        except httpx.TimeoutException as exc:
            raise ProviderError("Tempo limite excedido ao falar com a OpenAI.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("Falha de conexão com a API da OpenAI.") from exc

        if response.status_code >= 400:
            raise ProviderError(self._message_for(response))

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError("A OpenAI devolveu uma resposta inválida.") from exc
        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str):
            raise ProviderError("A resposta da OpenAI não contém texto de transcrição.")
        return {"text": text}

    async def check(self, api_key: str) -> int:
        """GET somente leitura em ``/models``; devolve a quantidade de modelos."""
        if not api_key:
            raise ApiKeyMissingError("Chave OpenAI ausente. Configure-a no cofre do sistema.")
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            async with self._client() as client:
                response = await client.get("/models", headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderError("Tempo limite excedido ao falar com a OpenAI.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("Falha de conexão com a API da OpenAI.") from exc
        if response.status_code >= 400:
            raise ProviderError(self._message_for(response))
        try:
            payload = response.json()
        except ValueError:
            return 0
        models = payload.get("data") if isinstance(payload, dict) else None
        return len(models) if isinstance(models, list) else 0

    @staticmethod
    def _message_for(response: httpx.Response) -> str:
        detail = OpenAIAdapter._detail(response)
        if response.status_code == 401:
            return "Chave OpenAI inválida ou sem permissão."
        if response.status_code == 403:
            return "A conta OpenAI não tem permissão para esta operação."
        if response.status_code == 429:
            return "Limite de uso/cota da OpenAI atingido. Tente mais tarde."
        suffix = f" Detalhe: {detail}" if detail else ""
        return f"A OpenAI respondeu HTTP {response.status_code}.{suffix}".strip()
