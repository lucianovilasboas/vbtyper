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
from vb_typer.services.normalize import INSTRUCTIONS, needs_normalization, smart_hint
from vb_typer.services.transcription import JobContext, TranscriptionService

logger = logging.getLogger(__name__)


class JobManager:
    def __init__(
        self, service: TranscriptionService, openai: OpenAIAdapter, settings: AppSettings
    ) -> None:
        self.service = service
        self.openai = openai
        self.settings = settings
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

    async def _maybe_adjust(self, text: str, context: JobContext, api_key: str) -> tuple[str, str]:
        """Aplica o modo inteligente; devolve ``(texto, modo entregue)``.

        Falha no ajuste **não** perde o ditado: devolve o texto literal e registra
        o motivo no log. Nesse caso o modo entregue é ``literal`` — é o que o
        histórico passa a mostrar, para o usuário saber que não foi ajustado.
        """
        if context.mode != TranscriptionMode.SMART:
            return text, TranscriptionMode.LITERAL
        if not needs_normalization(text):
            return text, TranscriptionMode.SMART
        try:
            adjusted = await self.openai.normalize(
                text=text,
                model=self.settings.smart_model,
                instructions=INSTRUCTIONS,
                api_key=api_key,
            )
        except DomainError as exc:
            logger.warning("Ajuste do modo inteligente falhou (job %s): %s", context.id, exc)
            return text, TranscriptionMode.LITERAL
        return adjusted or text, TranscriptionMode.SMART

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
            started = time.monotonic()
            result = await self.openai.transcribe(
                audio=audio,
                filename=context.filename,
                content_type=context.content_type,
                model=context.model,
                language=context.language,
                api_key=api_key,
                prompt=smart_hint(context.mode),
            )
            transcribe_ms = int((time.monotonic() - started) * 1000)
            text = (result.get("text") or "").strip()
            if not text:
                raise ProviderError("A API não reconheceu fala nesse áudio.")
            text, mode = await self._maybe_adjust(text, context, api_key)
            await asyncio.to_thread(
                self.service.finish_success,
                job_id,
                text=text,
                raw_text=(result.get("text") or "").strip(),
                mode=mode,
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
