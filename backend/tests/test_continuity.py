"""Memória entre ditados: janela, orçamento e o que entra no contexto."""

from __future__ import annotations

from datetime import datetime, timedelta

from vb_typer.domain.profiles import ProfileSpec
from vb_typer.services.continuity import ContinuityService, join_context


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def _record(container, text: str, when: datetime | None = None, **kwargs):
    return container.history.record(
        text=text,
        duration_s=10,
        model="gpt-4o-mini-transcribe",
        language="pt",
        transcribe_ms=1000,
        inserted=True,
        created_at=_stamp(when or datetime.now()),
        **kwargs,
    )


# ---------------------------------------------------------------- montagem


def test_join_context_keeps_the_oldest_to_newest_order():
    context = join_context(["primeiro", "segundo"], 1000)

    assert context.text == "primeiro\n\nsegundo"
    assert context.count == 2


def test_join_context_trims_the_oldest_when_over_budget():
    """O que interessa é a cauda recente: corta o começo do ditado mais antigo."""
    old = "A" * 300
    new = "B" * 300

    context = join_context([old, new], 500, min_chunk=100)

    assert context.text.endswith("B" * 300)
    assert context.text.startswith("…")
    assert len(context.text) <= 520
    assert context.count == 2


def test_join_context_drops_a_chunk_that_barely_fits():
    context = join_context(["A" * 300], 100, min_chunk=200)

    assert context.text == ""
    assert context.count == 0


def test_join_context_ignores_blank_texts():
    context = join_context(["", "   ", "texto"], 1000)

    assert context.text == "texto"
    assert context.count == 1


def test_join_context_without_text_is_empty():
    assert join_context([], 1000).enabled is False


# ------------------------------------------------------------------- flag


def test_continuity_is_opt_in_per_profile():
    off = ProfileSpec(slug="email", name="E-mail", instructions="x", hint=None)
    on = ProfileSpec(slug="email", name="E-mail", instructions="x", options={"continuo": True})

    assert ContinuityService.accepts(off) is False
    assert ContinuityService.accepts(on) is True


def test_literal_never_accepts_continuity():
    """A transcrição fiel é o próprio reconhecido: não há segunda chamada."""
    literal = ProfileSpec(
        slug="literal", name="Transcrição fiel", instructions="", options={"continuo": True}
    )

    assert ContinuityService.accepts(literal) is False


# --------------------------------------------------------------- histórico


def test_context_uses_the_recent_transcriptions_in_order(container):
    now = datetime.now()
    _record(container, "primeira parte", now - timedelta(minutes=10))
    _record(container, "segunda parte", now - timedelta(minutes=2))

    context = ContinuityService(container.session_factory).context_for(now=now)

    assert context.text == "primeira parte\n\nsegunda parte"
    assert context.count == 2


def test_context_ignores_rows_outside_the_window(container):
    now = datetime.now()
    _record(container, "ditado de ontem", now - timedelta(hours=20))
    _record(container, "agora", now - timedelta(minutes=1))

    context = ContinuityService(container.session_factory).context_for(now=now)

    assert context.text == "agora"
    assert context.count == 1


def test_context_ignores_failed_and_empty_rows(container):
    now = datetime.now()
    _record(container, "válido", now - timedelta(minutes=5))
    _record(container, "falhou", now - timedelta(minutes=4), error="áudio vazio")
    _record(container, "", now - timedelta(minutes=3))

    context = ContinuityService(container.session_factory).context_for(now=now)

    assert context.text == "válido"


def test_context_limits_to_the_last_three_dictations(container):
    now = datetime.now()
    for index in range(5):
        _record(container, f"ditado {index}", now - timedelta(minutes=10 - index))

    context = ContinuityService(container.session_factory).context_for(now=now)

    assert context.count == 3
    assert context.text.startswith("ditado 2")
    assert context.text.endswith("ditado 4")


def test_context_can_exclude_the_transcription_being_redone(container):
    now = datetime.now()
    first = _record(container, "anterior", now - timedelta(minutes=3))
    current = _record(container, "atual", now - timedelta(minutes=1))

    context = ContinuityService(container.session_factory).context_for(
        exclude_id=current.id, now=now
    )

    assert context.text == "anterior"
    assert first.id != current.id


def test_context_is_empty_when_nothing_was_dictated(container):
    context = ContinuityService(container.session_factory).context_for()

    assert context.enabled is False
    assert context.count == 0


# ------------------------------------------------------------------ prompt


def test_instructions_only_mention_continuity_when_asked():
    from vb_typer.domain.profiles import compose_instructions

    profile = ProfileSpec(slug="email", name="E-mail", instructions="Faça um e-mail.")

    without = compose_instructions(profile)
    with_context = compose_instructions(profile, continuity=True)

    assert "continuidade" not in without
    assert "continuidade" in with_context
    assert "Faça um e-mail." in without
    assert "Faça um e-mail." in with_context
    # A regra base continua: o novo trecho é a única fonte de conteúdo.
    assert with_context.startswith(without.split("\n\n")[0])


def test_user_content_marks_the_previous_text_as_context():
    from vb_typer.domain.profiles import compose_user_content

    content = compose_user_content("novo trecho", "trecho anterior")

    assert content.index("trecho anterior") < content.index("novo trecho")
    assert "[DITADOS ANTERIORES" in content
    assert "[NOVO DITADO" in content
    # Sem contexto, a mensagem é exatamente o texto ditado.
    assert compose_user_content("novo trecho") == "novo trecho"
