"""Fila de jobs e worker assíncrono.

O cancelamento interrompe o aguardo e a inserção no cliente, mas não desfaz
cobrança de uma requisição já entregue à OpenAI.
"""

from __future__ import annotations

import asyncio
import logging
import time

from vb_typer.adapters.openai import OpenAIAdapter
from vb_typer.core.config import AppSettings
from vb_typer.domain.enums import TranscriptionMode
from vb_typer.domain.errors import DomainError, ProviderError
from vb_typer.domain.profiles import (
    LITERAL_SLUG,
    REVISED_SLUG,
    compose_instructions,
    is_literal,
)
from vb_typer.services.normalize import needs_normalization
from vb_typer.services.profiles import ProfileService
from vb_typer.services.settings import SettingsService
from vb_typer.services.transcription import JobContext, TranscriptionService

logger = logging.getLogger(__name__)


class JobManager:
    def __init__(
        self,
        service: TranscriptionService,
        openai: OpenAIAdapter,
        settings: AppSettings,
        profiles: ProfileService,
        settings_service: SettingsService,
    ) -> None:
        self.service = service
        self.openai = openai
        self.settings = settings
        self.profiles = profiles
        self.settings_service = settings_service
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.workers: list[asyncio.Task] = []
        self.running: dict[str, asyncio.Task] = {}
        self._stopping = False

    async def start(self) -> None:
        self._stopping = False
        for index in range(self.settings.worker_concurrency):
            self.workers.append(
                asyncio.create_task(self._worker_loop(), name=f"vb-typer-worker-{index}")
            )
        for job_id in await asyncio.to_thread(self.service.recover_orphans):
            await self.queue.put(job_id)

    async def stop(self) -> None:
        self._stopping = True
        for task in list(self.running.values()):
            task.cancel()
        for worker in self.workers:
            worker.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()
        if self.running:
            await asyncio.gather(*list(self.running.values()), return_exceptions=True)
            self.running.clear()

    async def submit(self, job_id: str) -> None:
        await self.queue.put(job_id)

    async def _apply_profile(
        self, text: str, context: JobContext, profile, api_key: str, model: str
    ) -> tuple[str, str, dict | None, str]:
        """Aplica o perfil do job; devolve ``(texto, modo, usage, perfil entregue)``.

        Falha no perfil **não** perde o ditado: devolve o texto literal e registra
        o motivo no log. Nesse caso o perfil entregue é ``literal`` — é o que o
        histórico passa a mostrar, para o usuário saber que não foi transformado.
        """
        if is_literal(profile.slug):
            return text, TranscriptionMode.LITERAL, None, LITERAL_SLUG
        # O filtro conservador só vale para o "Texto revisado": os perfis
        # editoriais sempre têm o que fazer.
        if profile.slug == REVISED_SLUG and not needs_normalization(text):
            return text, TranscriptionMode.SMART, None, profile.slug
        await asyncio.to_thread(self.service.set_phase, context.id, "rendering")
        try:
            adjusted, usage = await self.openai.normalize(
                text=text,
                model=model,
                instructions=compose_instructions(profile),
                api_key=api_key,
            )
        except DomainError as exc:
            logger.warning("Perfil %s falhou (job %s): %s", profile.slug, context.id, exc)
            return text, TranscriptionMode.LITERAL, None, LITERAL_SLUG
        return adjusted or text, TranscriptionMode.SMART, usage, profile.slug

    async def cancel(self, job_id: str) -> None:
        await asyncio.to_thread(self.service.request_cancel, job_id)
        task = self.running.get(job_id)
        if task is not None:
            task.cancel()

    async def _worker_loop(self) -> None:
        while True:
            job_id = await self.queue.get()
            try:
                if self._stopping:
                    return
                task = asyncio.create_task(self._process(job_id))
                self.running[job_id] = task
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    # Cancelamento do job não deve derrubar o worker.
                    if self._stopping:
                        raise
                except Exception:  # pragma: no cover - proteção do laço
                    logger.exception("Falha inesperada no job %s", job_id)
                finally:
                    self.running.pop(job_id, None)
            finally:
                self.queue.task_done()

    async def _process(self, job_id: str) -> None:
        context = await asyncio.to_thread(self.service.claim, job_id)
        if context is None:
            return
        try:
            audio = await asyncio.to_thread(self.service.read_audio, context)
            api_key = await asyncio.to_thread(self.service.secrets.get_api_key)
            profile = await asyncio.to_thread(self.profiles.get, context.profile)
            started = time.monotonic()
            result = await self.openai.transcribe(
                audio=audio,
                filename=context.filename,
                content_type=context.content_type,
                model=context.model,
                language=context.language,
                api_key=api_key,
                prompt=None if is_literal(profile.slug) else profile.hint,
            )
            transcribe_ms = int((time.monotonic() - started) * 1000)
            text = (result.get("text") or "").strip()
            if not text:
                raise ProviderError("A API não reconheceu fala nesse áudio.")
            # O perfil pode fixar o modelo; senão vale o padrão das configurações.
            model = profile.model or await asyncio.to_thread(self.settings_service.smart_model_now)
            text, mode, usage, delivered = await self._apply_profile(
                text, context, profile, api_key, model
            )
            await asyncio.to_thread(
                self.service.finish_success,
                job_id,
                text=text,
                raw_text=(result.get("text") or "").strip(),
                mode=mode,
                profile=delivered,
                usage=usage,
                text_model=model,
                duration_s=context.duration_s,
                transcribe_ms=transcribe_ms,
            )
        except asyncio.CancelledError:
            if self._stopping:
                await asyncio.to_thread(self.service.mark_interrupted, job_id)
            else:
                await asyncio.to_thread(self.service.mark_canceled, job_id)
            raise
        except DomainError as exc:
            await asyncio.to_thread(
                self.service.finish_failure,
                job_id,
                error=exc.message,
                duration_s=context.duration_s,
            )
        except Exception:  # pragma: no cover - proteção do worker
            logger.exception("Erro interno no job %s", job_id)
            await asyncio.to_thread(
                self.service.finish_failure,
                job_id,
                error="Erro interno ao transcrever.",
                duration_s=context.duration_s,
            )
