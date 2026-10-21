"""Ciclo de vida dos jobs de transcrição."""

from __future__ import annotations

import asyncio

import httpx
import pytest

ENDPOINT = "/api/v1/transcription-jobs"


def _upload(
    wav: bytes,
    *,
    model: str | None = None,
    language: str | None = None,
    filename: str = "recording.wav",
    content_type: str = "audio/wav",
):
    files = {"file": (filename, wav, content_type)}
    data: dict[str, str] = {}
    if model:
        data["model"] = model
    if language:
        data["language"] = language
    return files, data


async def test_successful_transcription_is_persisted(
    client, auth, container, make_wav, with_api_key, respx_mock, wait_for_job
):
    respx_mock.post("https://api.openai.com/v1/audio/transcriptions").mock(
        return_value=httpx.Response(200, json={"text": "olá mundo ditado"})
    )
    files, data = _upload(make_wav(1.0), model="gpt-transcribe", language="pt")
    response = await client.post(ENDPOINT, headers=auth, files=files, data=data)
    assert response.status_code == 202
    created = response.json()
    assert created["status"] in {"queued", "running"}
    assert created["model"] == "gpt-transcribe"

    job = await wait_for_job(client, created["id"], auth, {"succeeded"})
    assert job["result"]["text"] == "olá mundo ditado"
    assert job["result"]["words"] == 3
    assert job["transcription_id"] == job["result"]["id"]
    assert job["duration_s"] > 0.5
    assert job["error"] is None

    items, total = container.history.list()
    assert total == 1
    assert items[0].inserted is False
    assert items[0].audio_path and items[0].audio_path.endswith(".wav")
    from pathlib import Path

    assert Path(items[0].audio_path).is_file()


async def test_empty_audio_is_rejected(client, auth, with_api_key):
    files, data = _upload(b"", content_type="audio/wav")
    response = await client.post(ENDPOINT, headers=auth, files=files, data=data)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_audio"


async def test_oversize_audio_is_rejected(client, auth, container, make_wav, with_api_key):
    container.settings.max_upload_bytes = 2048
    files, data = _upload(make_wav(1.0))
    response = await client.post(ENDPOINT, headers=auth, files=files, data=data)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "audio_too_large"


async def test_unsupported_content_type_is_rejected(client, auth, with_api_key):
    files, data = _upload(b"nao-e-audio", filename="nota.txt", content_type="text/plain")
    response = await client.post(ENDPOINT, headers=auth, files=files, data=data)
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media_type"


async def test_unknown_model_is_rejected(client, auth, make_wav, with_api_key):
    files, data = _upload(make_wav(0.5), model="modelo-x")
    response = await client.post(ENDPOINT, headers=auth, files=files, data=data)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_model"


async def test_provider_error_marks_job_failed(
    client, auth, container, make_wav, with_api_key, respx_mock, wait_for_job
):
    respx_mock.post("https://api.openai.com/v1/audio/transcriptions").mock(
        return_value=httpx.Response(500, json={"error": {"message": "boom interno"}})
    )
    files, data = _upload(make_wav(1.0))
    response = await client.post(ENDPOINT, headers=auth, files=files, data=data)
    job = await wait_for_job(client, response.json()["id"], auth, {"failed"})
    assert "500" in job["error"]
    items, total = container.history.list()
    assert total == 1
    assert items[0].error and items[0].inserted is False
    assert items[0].text == ""


async def test_missing_api_key_fails_job(client, auth, make_wav, wait_for_job):
    files, data = _upload(make_wav(1.0))
    response = await client.post(ENDPOINT, headers=auth, files=files, data=data)
    job = await wait_for_job(client, response.json()["id"], auth, {"failed"})
    assert "Chave OpenAI" in job["error"]


async def test_cancel_running_job_prevents_transcription(
    client, auth, container, make_wav, with_api_key, respx_mock, wait_for_job
):
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.5)
        return httpx.Response(200, json={"text": "não deveria aparecer"})

    respx_mock.post("https://api.openai.com/v1/audio/transcriptions").mock(side_effect=slow)
    files, data = _upload(make_wav(1.0))
    response = await client.post(ENDPOINT, headers=auth, files=files, data=data)
    job_id = response.json()["id"]
    await wait_for_job(client, job_id, auth, {"running"}, timeout=2)

    deleted = await client.delete(f"{ENDPOINT}/{job_id}", headers=auth)
    assert deleted.status_code == 200

    job = await wait_for_job(client, job_id, auth, {"canceled"})
    assert job["transcription_id"] is None
    _, total = container.history.list()
    assert total == 0


async def test_cancel_finished_job_is_a_noop(
    client, auth, make_wav, with_api_key, respx_mock, wait_for_job
):
    respx_mock.post("https://api.openai.com/v1/audio/transcriptions").mock(
        return_value=httpx.Response(200, json={"text": "pronto"})
    )
    files, data = _upload(make_wav(1.0))
    response = await client.post(ENDPOINT, headers=auth, files=files, data=data)
    job_id = response.json()["id"]
    await wait_for_job(client, job_id, auth, {"succeeded"})
    deleted = await client.delete(f"{ENDPOINT}/{job_id}", headers=auth)
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "succeeded"


async def test_unknown_job_returns_404(client, auth):
    response = await client.get(f"{ENDPOINT}/nao-existe", headers=auth)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_list_jobs(client, auth, make_wav, with_api_key, respx_mock, wait_for_job):
    respx_mock.post("https://api.openai.com/v1/audio/transcriptions").mock(
        return_value=httpx.Response(200, json={"text": "um"})
    )
    files, data = _upload(make_wav(0.5))
    response = await client.post(ENDPOINT, headers=auth, files=files, data=data)
    await wait_for_job(client, response.json()["id"], auth, {"succeeded"})
    listing = await client.get(ENDPOINT, headers=auth)
    assert listing.status_code == 200
    assert listing.json()["total"] == 1


async def test_duration_from_client_fills_webm_gap(
    client, auth, with_api_key, respx_mock, wait_for_job
):
    """WebM não traz duração no cabeçalho: vale o cronômetro do navegador."""
    respx_mock.post("https://api.openai.com/v1/audio/transcriptions").mock(
        return_value=httpx.Response(200, json={"text": "doze segundos e meio"})
    )
    files = {"file": ("gravacao.webm", b"\x1aE\xdf\xa3webm-sem-cabecalho", "audio/webm")}
    response = await client.post(ENDPOINT, headers=auth, files=files, data={"duration_s": "12.5"})

    assert response.status_code == 202
    created = response.json()
    assert created["duration_s"] == 12.5

    job = await wait_for_job(client, created["id"], auth, {"succeeded"})
    assert job["result"]["duration_s"] == 12.5
    assert job["result"]["cost_usd"] > 0


async def test_wav_header_wins_over_client_hint(
    client, auth, make_wav, with_api_key, respx_mock, wait_for_job
):
    """O que o arquivo diz manda: o WAV do desktop não é sobrescrito pelo cliente."""
    respx_mock.post("https://api.openai.com/v1/audio/transcriptions").mock(
        return_value=httpx.Response(200, json={"text": "meio segundo"})
    )
    files, data = _upload(make_wav(0.5))
    data["duration_s"] = "99"

    response = await client.post(ENDPOINT, headers=auth, files=files, data=data)

    assert response.status_code == 202
    assert response.json()["duration_s"] == 0.5
    await wait_for_job(client, response.json()["id"], auth, {"succeeded"})


@pytest.mark.parametrize("hint", ["0", "-3", "999999"])
async def test_absurd_duration_hint_is_ignored(
    client, auth, with_api_key, respx_mock, wait_for_job, hint
):
    """Palpite ruim nunca derruba o ditado: só é ignorado."""
    respx_mock.post("https://api.openai.com/v1/audio/transcriptions").mock(
        return_value=httpx.Response(200, json={"text": "sem duração confiável"})
    )
    files = {"file": ("gravacao.webm", b"\x1aE\xdf\xa3webm", "audio/webm")}

    response = await client.post(ENDPOINT, headers=auth, files=files, data={"duration_s": hint})

    assert response.status_code == 202
    assert response.json()["duration_s"] == 0.0
    await wait_for_job(client, response.json()["id"], auth, {"succeeded"})


async def test_job_with_profile_creates_a_version(
    client, auth, make_wav, with_api_key, respx_mock, wait_for_job
):
    """Perfil editorial: a segunda chamada vira versão, com custo e texto cru."""
    respx_mock.post("https://api.openai.com/v1/audio/transcriptions").mock(
        return_value=httpx.Response(200, json={"text": "Oi Rafael, verifica o erro."})
    )
    respx_mock.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Assunto: erro\n\nOi Rafael..."}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 40},
            },
        )
    )
    files = {"file": ("gravacao.wav", make_wav(0.5), "audio/wav")}

    response = await client.post(ENDPOINT, headers=auth, files=files, data={"profile": "email"})

    assert response.status_code == 202
    created = response.json()
    assert created["profile"] == "email"

    job = await wait_for_job(client, created["id"], auth, {"succeeded"})
    result = job["result"]
    assert result["profile"] == "email"
    assert result["raw_text"] == "Oi Rafael, verifica o erro."
    assert result["text"].startswith("Assunto:")

    detail = await client.get(f"/api/v1/transcriptions/{result['id']}", headers=auth)
    versions = detail.json()["versions"]
    assert len(versions) == 1
    assert versions[0]["profile"] == "email"
    assert versions[0]["prompt_tokens"] == 50
    assert versions[0]["cost_usd"] > 0

    # A fase some quando o job termina.
    assert job["phase"] == ""


def test_claim_marks_the_transcribing_phase(container, make_wav):
    """O cliente vê 'transcribing' enquanto o áudio está na OpenAI."""
    job = container.transcription.create_job(
        data=make_wav(0.5),
        filename="a.wav",
        content_type="audio/wav",
        model=None,
        language="pt",
    )

    context = container.transcription.claim(job.id)

    assert context is not None
    assert container.transcription.get(job.id).phase == "transcribing"


def test_set_phase_is_visible_and_ignored_after_the_end(container, make_wav):
    job = container.transcription.create_job(
        data=make_wav(0.5),
        filename="a.wav",
        content_type="audio/wav",
        model=None,
        language="pt",
    )
    container.transcription.claim(job.id)

    container.transcription.set_phase(job.id, "rendering")
    assert container.transcription.get(job.id).phase == "rendering"

    container.transcription.mark_canceled(job.id)
    assert container.transcription.get(job.id).phase == ""
    # Job terminal não muda mais de fase.
    container.transcription.set_phase(job.id, "rendering")
    assert container.transcription.get(job.id).phase == ""


def test_invalid_default_profile_falls_back_to_literal(container, make_wav):
    """Valor legado inválido no padrão nunca impede o ditado."""
    from vb_typer.db.models import AppSetting

    container.settings_service.current()  # garante a linha id=1
    with container.session_factory() as session:
        row = session.get(AppSetting, 1)
        row.default_profile = "smart"  # valor que a 0003 deixava para quem usava o modo smart
        session.commit()

    job = container.transcription.create_job(
        data=make_wav(0.5),
        filename="a.wav",
        content_type="audio/wav",
        model=None,
        language="pt",
    )

    assert job.profile == "literal"
