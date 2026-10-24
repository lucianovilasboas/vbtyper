"""Adaptador da API OpenAI (transcrição, ajuste de texto e verificação)."""

from __future__ import annotations

import json

import httpx

from vb_typer.domain.errors import ApiKeyMissingError, ProviderError
from vb_typer.domain.profiles import compose_user_content


class OpenAIAdapter:
    def __init__(self, base_url: str, timeout_s: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        # Um cliente só, reaproveitado: reabrir a conexão a cada ditado custaria
        # um handshake TLS novo (~100–300 ms) no caminho até o texto.
        self._client: httpx.AsyncClient | None = None

    def _connection(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_s)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

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

    async def _send(self, method: str, url: str, **kwargs) -> httpx.Response:
        client = self._connection()
        try:
            return await client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            raise ProviderError("Tempo limite excedido ao falar com a OpenAI.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("Falha de conexão com a API da OpenAI.") from exc

    async def transcribe(
        self,
        *,
        audio: bytes,
        filename: str,
        content_type: str,
        model: str,
        language: str,
        api_key: str,
        prompt: str | None = None,
    ) -> dict:
        if not api_key:
            raise ApiKeyMissingError("Chave OpenAI ausente. Configure-a no cofre do sistema.")
        files = {"file": (filename or "recording.wav", audio, content_type or "audio/wav")}
        data = {"model": model, "language": language}
        if prompt:
            data["prompt"] = prompt
        headers = {"Authorization": f"Bearer {api_key}"}
        response = await self._send(
            "POST", "/audio/transcriptions", files=files, data=data, headers=headers
        )
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

    async def normalize(
        self,
        *,
        text: str,
        model: str,
        instructions: str,
        api_key: str,
        context: str | None = None,
    ) -> tuple[str, dict]:
        """Aplica um perfil a um texto já transcrito; devolve ``(texto, usage)``.

        ``context`` é o texto dos ditados anteriores (continuação): vai na
        mensagem do usuário em blocos marcados, nunca como fonte de conteúdo.
        """
        if not api_key:
            raise ApiKeyMissingError("Chave OpenAI ausente. Configure-a no cofre do sistema.")
        body = {
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": compose_user_content(text, context)},
            ],
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        response = await self._send("POST", "/chat/completions", json=body, headers=headers)
        if response.status_code >= 400:
            raise ProviderError(self._message_for(response))

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError("A OpenAI devolveu uma resposta inválida.") from exc
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not isinstance(choices, list) or not choices:
            raise ProviderError("A resposta do ajuste não contém texto.")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        adjusted = message.get("content") if isinstance(message, dict) else None
        if not isinstance(adjusted, str) or not adjusted.strip():
            raise ProviderError("O ajuste do texto voltou vazio.")
        usage = payload.get("usage") if isinstance(payload, dict) else None
        return adjusted.strip(), usage if isinstance(usage, dict) else {}

    async def check(self, api_key: str) -> int:
        """GET somente leitura em ``/models``; devolve a quantidade de modelos."""
        if not api_key:
            raise ApiKeyMissingError("Chave OpenAI ausente. Configure-a no cofre do sistema.")
        headers = {"Authorization": f"Bearer {api_key}"}
        response = await self._send("GET", "/models", headers=headers)
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
