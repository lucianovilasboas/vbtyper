"""Cliente REST: envio, acompanhamento, cancelamento e registro de inserção."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from vb_typer_desktop import api

BASE = "http://127.0.0.1:8765"


def test_token_env_takes_precedence(monkeypatch):
    monkeypatch.setenv("VB_TYPER_API_TOKEN", "do-ambiente")
    assert api.load_token() == "do-ambiente"


def test_token_read_from_file():
    target = api.token_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("do-arquivo\n", encoding="utf-8")
    assert api.load_token() == "do-arquivo"


def test_token_absent():
    assert api.load_token() is None


@respx.mock
def test_create_job_sends_multipart_with_bearer():
    route = respx.post(f"{BASE}/api/v1/transcription-jobs").mock(
        return_value=httpx.Response(202, json={"id": "job-1", "status": "queued"})
    )
    client = api.ApiClient(token="segredo")
    job = client.create_job(
        b"RIFF",
        "audio.wav",
        "audio/wav",
        model="gpt-transcribe",
        language="pt",
        profile="email",
    )
    assert (job.id, job.status) == ("job-1", "queued")
    request = route.calls[0].request
    assert request.headers["authorization"] == "Bearer segredo"
    assert b'name="model"' in request.content
    assert b"gpt-transcribe" in request.content
    assert b'name="profile"' in request.content
    assert b"email" in request.content
    assert b'filename="audio.wav"' in request.content
    client.close()


@respx.mock
def test_create_job_omits_empty_options():
    route = respx.post(f"{BASE}/api/v1/transcription-jobs").mock(
        return_value=httpx.Response(202, json={"id": "job-1", "status": "queued"})
    )
    api.ApiClient(token="t").create_job(b"RIFF", "a.wav", "audio/wav")
    content = route.calls[0].request.content
    assert b'name="model"' not in content
    assert b'name="profile"' not in content


@respx.mock
def test_get_job_reads_status_and_result():
    respx.get(f"{BASE}/api/v1/transcription-jobs/job-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "job-1",
                "status": "succeeded",
                "transcription_id": 7,
                "result": {"id": 7, "text": "Ola, acao!"},
            },
        )
    )
    job = api.ApiClient(token="t").get_job("job-1")
    assert job.finished is True
    assert job.text == "Ola, acao!"
    assert job.transcription_id == 7


@respx.mock
def test_running_job_is_not_finished():
    respx.get(f"{BASE}/api/v1/transcription-jobs/job-1").mock(
        return_value=httpx.Response(200, json={"id": "job-1", "status": "running"})
    )
    assert api.ApiClient(token="t").get_job("job-1").finished is False


@respx.mock
def test_cancel_job_calls_delete():
    route = respx.delete(f"{BASE}/api/v1/transcription-jobs/job-1").mock(
        return_value=httpx.Response(200, json={"id": "job-1", "status": "canceled"})
    )
    assert api.ApiClient(token="t").cancel_job("job-1").status == "canceled"
    assert route.called


@respx.mock
def test_mark_inserted_sends_patch_body():
    route = respx.patch(f"{BASE}/api/v1/transcriptions/7").mock(
        return_value=httpx.Response(200, json={"id": 7})
    )
    api.ApiClient(token="t").mark_inserted(7, True, 123)
    assert json.loads(route.calls[0].request.content) == {"inserted": True, "insert_ms": 123}


@respx.mock
def test_mark_inserted_without_timing():
    route = respx.patch(f"{BASE}/api/v1/transcriptions/7").mock(
        return_value=httpx.Response(200, json={"id": 7})
    )
    api.ApiClient(token="t").mark_inserted(7, False)
    assert json.loads(route.calls[0].request.content) == {"inserted": False}


@respx.mock
def test_domain_error_becomes_api_error():
    respx.post(f"{BASE}/api/v1/transcription-jobs").mock(
        return_value=httpx.Response(
            413, json={"error": {"code": "audio_too_large", "message": "Áudio grande demais."}}
        )
    )
    with pytest.raises(api.ApiError, match="grande demais"):
        api.ApiClient(token="t").create_job(b"x", "a.wav", "audio/wav")


@respx.mock
def test_http_error_without_envelope_becomes_api_error():
    respx.get(f"{BASE}/api/v1/ready").mock(return_value=httpx.Response(500, text="boom"))
    with pytest.raises(api.ApiError, match="HTTP 500"):
        api.ApiClient(token="t").ready()


@respx.mock
def test_get_job_reads_the_processing_phase():
    respx.get(f"{BASE}/api/v1/transcription-jobs/job-1").mock(
        return_value=httpx.Response(
            200, json={"id": "job-1", "status": "running", "phase": "rendering"}
        )
    )
    assert api.ApiClient(token="t").get_job("job-1").phase == "rendering"


@respx.mock
def test_job_without_phase_defaults_to_empty():
    respx.get(f"{BASE}/api/v1/transcription-jobs/job-1").mock(
        return_value=httpx.Response(200, json={"id": "job-1", "status": "queued"})
    )
    assert api.ApiClient(token="t").get_job("job-1").phase == ""


@respx.mock
def test_network_failure_becomes_api_error():
    respx.get(f"{BASE}/api/v1/ready").mock(side_effect=httpx.ConnectError("recusada"))
    with pytest.raises(api.ApiError, match="Não foi possível falar com a API"):
        api.ApiClient(token="t").ready()


@respx.mock
def test_current_options_falls_back_on_failure():
    respx.get(f"{BASE}/api/v1/settings").mock(side_effect=httpx.ConnectError("off"))
    assert api.ApiClient(token="t").current_options() == ("", "", "", "")


@respx.mock
def test_current_options_read_settings():
    respx.get(f"{BASE}/api/v1/settings").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "gpt-transcribe",
                "language": "en",
                "mode": "smart",
                "default_profile": "email",
                "api_key_configured": True,
            },
        )
    )
    assert api.ApiClient(token="t").current_options() == (
        "gpt-transcribe",
        "en",
        "smart",
        "email",
    )


@respx.mock
def test_list_profiles_keeps_only_slug_and_name():
    respx.get(f"{BASE}/api/v1/profiles").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "slug": "literal",
                    "name": "Transcrição fiel",
                    "instructions": "",
                    "builtin": True,
                },
                {"slug": "email", "name": "E-mail profissional", "instructions": "…"},
                {"name": "sem slug"},
            ],
        )
    )
    assert api.ApiClient(token="t").list_profiles() == [
        {"slug": "literal", "name": "Transcrição fiel"},
        {"slug": "email", "name": "E-mail profissional"},
    ]


@respx.mock
def test_list_profiles_falls_back_to_empty_on_failure():
    respx.get(f"{BASE}/api/v1/profiles").mock(side_effect=httpx.ConnectError("off"))
    assert api.ApiClient(token="t").list_profiles() == []


def test_no_token_means_no_authorization_header():
    assert api.ApiClient(token="")._headers() == {}


def test_parse_job_reads_delivery_and_tools():
    job = api.parse_job(
        {
            "id": "job-1",
            "status": "succeeded",
            "result": {
                "text": "a b",
                "delivery": "tui",
                "tools": ["single_line", "trim"],
            },
        }
    )
    assert job.delivery == "tui"
    assert job.tools == ("single_line", "trim")


def test_parse_job_defaults_to_text():
    job = api.parse_job({"id": "job-1", "status": "queued"})
    assert job.delivery == "text"
    assert job.tools == ()
