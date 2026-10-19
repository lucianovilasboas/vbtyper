"""Modo inteligente: quando vale ajustar o texto e o que a dica pede."""

from __future__ import annotations

import pytest

from vb_typer.services.normalize import needs_normalization, smart_hint


@pytest.mark.parametrize(
    "frase",
    [
        "manda um oi pra ela",
        "Muito bom, parece que deu certinho.",
        "Ok, agora vamos implementar as telas, as abas na web",
        "E eu coloquei também a possibilidade de mudar a cor do tema",
        "",
        "   ",
    ],
)
def test_plain_prose_does_not_need_the_adjustment(frase):
    assert needs_normalization(frase) is False


@pytest.mark.parametrize(
    "frase",
    [
        "reunião no dia dezoito de outubro de dois mil e vinte e cinco",
        "custou cinquenta reais e vinte centavos",
        "desconto de trinta por cento",
        "às três e meia da tarde",
        "o c p f dele é quatro dois um",
        "o C P F dele",
        "o relatório c s v ficou pronto",
        "isso foi em 2025",
        "me passa o cnpj",
    ],
)
def test_spoken_numbers_dates_values_and_acronyms_need_the_adjustment(frase):
    assert needs_normalization(frase) is True


def test_the_article_alone_does_not_trigger():
    """'um'/'uma' são artigo: disparar por eles ajustaria quase todo ditado."""
    assert needs_normalization("me empresta um livro") is False
    assert needs_normalization("era uma vez uma menina") is False


def test_two_loose_letters_are_not_an_acronym():
    """'e a' aparece em prosa; só três letras soltas seguidas contam como sigla."""
    assert needs_normalization("ele e a menina") is False


def test_hint_only_exists_in_smart_mode():
    assert smart_hint("smart")
    assert smart_hint("literal") is None
    assert smart_hint("qualquer outra coisa") is None
