"""Modo de transcrição: literal por padrão; inteligente só quando pedido."""

from __future__ import annotations

import json

import httpx

ENDPOINT = "/api/v1/transcription-jobs"
AUDIO = "https://api.openai.com/v1/audio/transcriptions"
CHAT = "https://api.openai.com/v1/chat/completions"

FALADO = "reunião no dia dezoito de outubro de dois mil e vinte e cinco"
AJUSTADO = "reunião no dia 18/10/2025"


def _upload(wav: bytes, *, mode: str | None = None, model: str | None = None):
    files = {"file": ("recording.wav", wav, "audio/wav")}
    data: dict[str, str] = {}
    if model:
        data["model"] = model
    if mode:
        data["mode"] = mode
    return files, data


async def _run(client, auth, respx_mock, wav, *, mode=None, audio_text=FALADO, chat_text=AJUSTADO):
    respx_mock.post(AUDIO).mock(return_value=httpx.Response(200, json={"text": audio_text}))
    if chat_text is not None:
        respx_mock.post(CHAT).mock(
            return_value=httpx.Response(
                200, json={"choices": [{"message": {"content": chat_text}}]}
            )
        )
    else:
        respx_mock.post(CHAT).mock(return_value=httpx.Response(500, json={"error": {}}))
    files, data = _upload(wav, mode=mode)
    created = (await client.post(ENDPOINT, headers=auth, files=files, data=data)).json()
    return created


async def test_default_is_literal_and_never_calls_the_adjustment(
    client, auth, container, make_wav, with_api_key, respx_mock, wait_for_job
):
    created = await _run(client, auth, respx_mock, make_wav(1.0))
    assert created["mode"] == "literal"

    job = await wait_for_job(client, created["id"], auth, {"succeeded"})
    result = job["result"]
    assert result["text"] == FALADO
    assert result["mode"] == "literal"
    assert result["raw_text"] == FALADO
    # Nenhuma dica de formatação foi enviada na transcrição (o corpo é multipart,
    # com o WAV binário no meio, daí o decode tolerante).
    assert "Formate" not in respx_mock.calls[0].request.content.decode("utf-8", "replace")


async def test_smart_mode_adjusts_and_keeps_the_spoken_text(
    client, auth, container, make_wav, with_api_key, respx_mock, wait_for_job
):
    created = await _run(client, auth, respx_mock, make_wav(1.0), mode="smart")
    assert created["mode"] == "smart"

    job = await wait_for_job(client, created["id"], auth, {"succeeded"})
    result = job["result"]
    assert result["text"] == AJUSTADO
    assert result["raw_text"] == FALADO  # o cru fica guardado, para poder voltar
    assert result["mode"] == "smart"

    chat = [call for call in respx_mock.calls if "chat/completions" in str(call.request.url)]
    assert len(chat) == 1
    body = json.loads(chat[0].request.content)
    assert body["model"] == container.settings.smart_model
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][1]["content"] == FALADO


async def test_smart_mode_skips_the_adjustment_when_there_is_nothing_to_convert(
    client, auth, container, make_wav, with_api_key, respx_mock, wait_for_job
):
    """Texto sem número/data/valor/sigla não gasta a segunda chamada."""
    created = await _run(
        client, auth, respx_mock, make_wav(1.0), mode="smart", audio_text="manda um oi pra ela"
    )
    job = await wait_for_job(client, created["id"], auth, {"succeeded"})

    assert job["result"]["text"] == "manda um oi pra ela"
    assert job["result"]["mode"] == "smart"  # era o modo pedido, e nada a ajustar
    assert all("chat/completions" not in str(call.request.url) for call in respx_mock.calls)


async def test_edited_revisado_always_runs_the_adjustment(
    client, auth, container, make_wav, with_api_key, respx_mock, wait_for_job
):
    """Se o prompt do "Texto revisado" foi editado, o pulo por heurística não vale."""
    patched = await client.patch(
        "/api/v1/profiles/revisado",
        headers=auth,
        json={"instructions": "Ajuste o texto para o português escrito, com pontuação."},
    )
    assert patched.status_code == 200

    created = await _run(
        client, auth, respx_mock, make_wav(1.0), mode="smart", audio_text="manda um oi pra ela"
    )
    job = await wait_for_job(client, created["id"], auth, {"succeeded"})

    assert job["result"]["text"] == AJUSTADO
    chat = [call for call in respx_mock.calls if "chat/completions" in str(call.request.url)]
    assert len(chat) == 1


async def test_smart_failure_delivers_the_literal_text(
    client, auth, container, make_wav, with_api_key, respx_mock, wait_for_job
):
    """Falha no ajuste nunca perde o ditado."""
    created = await _run(client, auth, respx_mock, make_wav(1.0), mode="smart", chat_text=None)
    job = await wait_for_job(client, created["id"], auth, {"succeeded"})

    assert job["status"] == "succeeded"
    assert job["result"]["text"] == FALADO
    assert job["result"]["mode"] == "literal"  # foi o que de fato saiu


async def test_invalid_mode_is_rejected(client, auth, make_wav):
    files, data = _upload(make_wav(1.0), mode="banana")
    response = await client.post(ENDPOINT, headers=auth, files=files, data=data)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_mode"


async def test_default_mode_comes_from_the_settings(
    client, auth, container, make_wav, with_api_key, respx_mock, wait_for_job
):
    changed = await client.patch("/api/v1/settings", headers=auth, json={"mode": "smart"})
    assert changed.status_code == 200
    assert changed.json()["mode"] == "smart"

    created = await _run(client, auth, respx_mock, make_wav(1.0))
    assert created["mode"] == "smart"
    job = await wait_for_job(client, created["id"], auth, {"succeeded"})
    assert job["result"]["text"] == AJUSTADO


async def test_settings_rejects_an_unknown_mode(client, auth):
    response = await client.patch("/api/v1/settings", headers=auth, json={"mode": "esperto"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_mode"
