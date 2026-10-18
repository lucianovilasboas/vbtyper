"""Leitura de formato e duração dos áudios recebidos."""

from __future__ import annotations

import pytest

from vb_typer.adapters.audio_store import (
    AudioStore,
    duration_of,
    normalized_content_type,
)
from vb_typer.domain.errors import AudioTooLargeError, InvalidAudioError, UnsupportedMediaTypeError


def test_wav_duration_is_read_from_header(make_wav):
    data = make_wav(2.0)
    assert duration_of(data, "audio/wav") == 2.0


def test_unknown_container_has_no_duration(make_wav):
    assert duration_of(b"\x1aE\xdf\xa3webm-bytes", "audio/webm") == 0.0


def test_content_type_is_inferred_from_extension():
    assert normalized_content_type("application/octet-stream", "rec.webm") == "audio/webm"
    assert normalized_content_type("audio/wav; charset=binary") == "audio/wav"


def test_store_rejects_empty_and_oversized(tmp_path, make_wav):
    store = AudioStore(tmp_path / "audio", 1024, ("audio/wav",))
    with pytest.raises(InvalidAudioError):
        store.save(b"", "audio/wav")
    with pytest.raises(AudioTooLargeError):
        store.save(make_wav(1.0), "audio/wav")


def test_store_rejects_unknown_format(tmp_path):
    store = AudioStore(tmp_path / "audio", 1024 * 1024, ("audio/wav",))
    with pytest.raises(UnsupportedMediaTypeError):
        store.save(b"conteudo", "text/plain")


def test_store_persists_under_year_month(tmp_path, make_wav):
    store = AudioStore(tmp_path / "audio", 1024 * 1024, ("audio/wav", "audio/webm"))
    stored = store.save(make_wav(0.5), "audio/wav")
    assert stored.path.is_file()
    assert stored.path.suffix == ".wav"
    assert stored.duration_s == 0.5
    assert len(stored.path.relative_to(tmp_path / "audio").parts) == 3
