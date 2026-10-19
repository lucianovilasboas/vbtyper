"""Modo Inteligente: decide e instrui o ajuste do texto ditado.

O ditado literal escreve números e datas **por extenso** ("dois mil e vinte e
cinco"), porque é assim que se fala. O ajuste converte isso para o formato
convencional. Como isso é uma segunda chamada (latência a mais), antes de
gastá-la vale checar se o texto tem *algo* que possa ser convertido — e a checagem
é deliberadamente conservadora: na dúvida, ajusta.
"""

from __future__ import annotations

import re

from vb_typer.domain.enums import TranscriptionMode

# Palavras que indicam número falado. "um"/"uma" ficam de fora de propósito: são
# artigo ("um oi", "uma coisa") e disparariam o ajuste em quase todo ditado.
# fmt: off
NUMBER_WORDS = frozenset([
    "dois", "duas", "três", "tres", "quatro", "cinco", "seis", "sete", "oito",
    "nove", "dez", "onze", "doze", "treze", "catorze", "quatorze", "quinze",
    "dezesseis", "dezassete", "dezessete", "dezoito", "dezenove", "vinte",
    "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta",
    "noventa", "cem", "cento", "duzentos", "duzentas", "trezentos", "trezentas",
    "quatrocentos", "quatrocentas", "quinhentos", "quinhentas", "seiscentos",
    "seiscentas", "setecentos", "setecentas", "oitocentos", "oitocentas",
    "novecentos", "novecentas", "mil", "milhão", "milhões", "bilhão", "bilhões",
])

VALUE_WORDS = frozenset([
    "real", "reais", "centavo", "centavos", "dólar", "dólares", "euro", "euros",
    "libra", "libras", "porcento", "porcentagem",
])

# Siglas que costumam ser ditadas como palavra e ficam em maiúsculas.
ACRONYMS = frozenset([
    "cpf", "cnpj", "cep", "rg", "cnh", "pis", "inss", "fgts", "irpf", "icms",
    "ipi", "iss", "sus", "pib", "ibge", "url", "api", "pdf", "csv", "xml",
    "pix", "boleto",
])
# fmt: on

# Siglas ditadas letra por letra: maiúsculas soltas ("C P F") ou uma sequência de
# três ou mais letras soltas em minúsculas ("c p f"). Duas letras não bastam —
# "e a" aparece em prosa o tempo todo.
SPELLED_ACRONYM = re.compile(
    r"\b[A-ZÀ-Ý]\b(?:\s+\b[A-ZÀ-Ý]\b)+|(?:^|\s)[a-zà-ÿ](?:\s+[a-zà-ÿ]){2,}(?=\s|$)"
)
WORD = re.compile(r"[a-zà-ÿ]+")


def needs_normalization(text: str) -> bool:
    """Vale gastar o ajuste neste texto?

    Conservador de propósito: um falso "sim" custa latência; um falso "não"
    deixaria o ditado sem o formato que o usuário pediu. Por isso o dígito
    conta, mesmo vindo do reconhecimento.
    """
    if not text or not text.strip():
        return False
    if any(char.isdigit() for char in text):
        return True
    if SPELLED_ACRONYM.search(text):
        return True
    words = WORD.findall(text.lower())
    if any(word in NUMBER_WORDS or word in VALUE_WORDS for word in words):
        return True
    return any(word in ACRONYMS for word in words)


INSTRUCTIONS = """\
Você ajusta texto ditado por voz para o português escrito.

Converta datas, horas, números, valores e siglas para formatos convencionais.
Não mude o sentido, não acrescente nem remova informação, não comente nada e
mantenha o idioma. Preserve a pontuação e as quebras de linha do original.

Exemplos:
"reunião no dia dezoito de outubro de dois mil e vinte e cinco" -> "reunião no dia 18/10/2025"
"custou cinquenta reais e vinte centavos" -> "custou R$ 50,20"
"desconto de trinta por cento" -> "desconto de 30%"
"às três e meia da tarde" -> "às 15h30"
"o c p f dele é quatro dois um" -> "o CPF dele é 421"
"o relatório c s v ficou pronto" -> "o relatório CSV ficou pronto"

Responda apenas com o texto final, sem aspas e sem explicação."""

# Versão curta usada como dica na própria transcrição (custo zero).
HINT = (
    "Formate números, datas, horas, valores e siglas de forma convencional "
    "(18/10/2025, R$ 50,20, 30%, 15h30, CPF)."
)


def smart_hint(mode: str) -> str | None:
    """Dica de formatação para a transcrição, ou ``None`` no modo literal."""
    return HINT if mode == TranscriptionMode.SMART else None
