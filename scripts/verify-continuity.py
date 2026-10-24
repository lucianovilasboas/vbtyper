"""Verificação manual do modo contínuo: chama a OpenAI e mostra o que voltou.

Não é teste automatizado (gasta alguns centavos e precisa da chave): serve para
conferir, de tempos em tempos, se o modelo está mesmo descartando a repetição do
que já está escrito. Os testes de `tests/test_continuity.py` e `tests/test_modes.py`
cobrem o que é determinístico (montagem do contexto, prompt e marcador).

Uso (a chave vem do cofre da sessão ou de OPENAI_API_KEY):

    cd backend
    DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus \
      uv run python ../scripts/verify-continuity.py

Sai com código 1 quando algum cenário desvia — assim dá para rodar num roteiro.
"""

from __future__ import annotations

import sys

import httpx

from vb_typer.adapters.secrets import SecretsAdapter
from vb_typer.core.config import AppSettings
from vb_typer.domain.profiles import (
    BUILTIN_BY_SLUG,
    compose_instructions,
    compose_user_content,
    is_nothing_new,
)

MODEL = "gpt-4o-mini"
URL = "https://api.openai.com/v1/chat/completions"
# O que já estaria no documento quando o novo ditado chega.
CONTEXT = "O prazo do relatório é sexta-feira. O responsável é o Rafael."

# (nome, ditado novo, termos que NÃO podem aparecer, termos que precisam aparecer)
CASES = [
    (
        "continuação com informação nova",
        "Também precisamos incluir o orçamento de outubro.",
        [],
        ["orçamento"],
    ),
    (
        "repetição parcial + algo novo",
        "O prazo do relatório é sexta-feira, o responsável é o Rafael, "
        "e também precisamos incluir o orçamento de outubro.",
        ["sexta", "rafael"],
        ["orçamento"],
    ),
    ("repetição total", "O prazo do relatório é sexta-feira.", None, None),
    ("assunto sem relação", "A reunião de produto foi cancelada.", [], ["cancelada"]),
]


def ask(api_key: str, instructions: str, text: str) -> str:
    response = httpx.post(
        URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": MODEL,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": compose_user_content(text, CONTEXT)},
            ],
        },
        timeout=60,
    )
    if response.status_code >= 400:
        raise SystemExit(f"OpenAI {response.status_code}: {response.text[:200]}")
    return response.json()["choices"][0]["message"]["content"].strip()


def main() -> int:
    api_key = SecretsAdapter(AppSettings()).get_api_key()
    if not api_key:
        print("Sem chave no cofre nem em OPENAI_API_KEY; nada foi chamado.", file=sys.stderr)
        return 2

    profile = BUILTIN_BY_SLUG["revisado"]
    instructions = compose_instructions(profile, continuity=True)
    print(f"modelo: {MODEL} · perfil: {profile.name}")
    print(f"contexto: {CONTEXT!r}\n")

    problems = 0
    for title, text, forbidden, required in CASES:
        answer = ask(api_key, instructions, text)
        print(f"{title}\n  dito:     {text}\n  devolveu: {answer!r}")
        if forbidden is None:  # repetição total: só o marcador serve
            ok = is_nothing_new(answer)
            print(f"  marcador reconhecido: {ok}")
            problems += 0 if ok else 1
        else:
            lowered = answer.casefold()
            repeated = [term for term in forbidden if term in lowered]
            missing = [term for term in required or () if term not in lowered]
            print(f"  repetiu: {repeated or 'nada'} · faltou: {missing or 'nada'}")
            problems += len(repeated) + len(missing)
        print()

    print("RESULTADO:", "ok" if problems == 0 else f"{problems} desvio(s) — revisar o prompt")
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
