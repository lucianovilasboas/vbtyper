"""Perfis de texto: o que a segunda chamada faz com a transcrição.

A transcrição fiel (ASR) é a **fonte da verdade**: todo perfil editorial parte
dela, nunca de outra versão já editada. Por isso as regras abaixo são comuns a
todos — o "não invente" não depende de repetir isso em cada perfil.

Os perfis padrão são semeados no banco a partir desta lista, uma única vez; a
partir daí são editáveis e removíveis, com exceção da transcrição fiel. O slug é
a chave nos dois casos.
"""

from __future__ import annotations

from dataclasses import dataclass, field

LITERAL_SLUG = "literal"
REVISED_SLUG = "revisado"

# Regras que valem para qualquer perfil editorial.
BASE_RULES = """\
Você reescreve um texto ditado por voz. Abaixo está a transcrição fiel do que
foi dito: ela é a ÚNICA fonte de informação.

Regras invioláveis:
- Não acrescente informação que não esteja no texto ditado.
- Preserve nomes, números, datas, valores e siglas exatamente como foram ditos
  (só corrija o formato quando o perfil pedir).
- Não invente decisões, responsáveis, prazos nem requisitos.
- Se o formato pedir um elemento que não foi dito (um assunto, um responsável,
  uma data), escreva [a esclarecer] **naquele item**, sem trocar o resto. Se o
  texto ditado não tiver conteúdo aproveitável, devolva-o como veio.
- Escreva em português escrito: elimine gírias e vícios de fala ("né", "tá",
  "tipo assim"), preservando o conteúdo.
- Responda apenas com o texto final: sem aspas, sem comentários e sem explicar
  o que você fez.
"""

# Dica curta mandada na própria transcrição (custo zero). Formata números.
FORMAT_HINT = (
    "Formate números, datas, horas, valores e siglas de forma convencional "
    "(18/10/2025, R$ 50,20, 30%, 15h30, CPF)."
)


@dataclass(frozen=True)
class ProfileSpec:
    """Definição de um perfil, embutido ou personalizado."""

    slug: str
    name: str
    instructions: str
    hint: str | None = None
    options: dict = field(default_factory=dict)
    builtin: bool = True
    # Modelo de texto deste perfil; ``None`` usa o padrão das configurações.
    model: str | None = None


_REVISED = """\
Ajuste o texto para o português escrito, sem mudar o sentido nem o conteúdo.

- Converta datas, horas, números, valores e siglas para o formato convencional.
- Remova vícios de linguagem e repetições involuntárias ("né", "tipo assim",
  "aí", "então" repetido, gagueira).
- Corrija a pontuação e as maiúsculas; mantenha as quebras de linha do original.
- Não reescreva o estilo: é o mesmo texto, só limpo.

Exemplos:
"reunião no dia dezoito de outubro de dois mil e vinte e cinco" -> "reunião no dia 18/10/2025"
"custou cinquenta reais e vinte centavos" -> "custou R$ 50,20"
"o c p f dele é quatro dois um" -> "o CPF dele é 421"
"""

_EMAIL = """\
Transforme o ditado em um e-mail profissional, pronto para enviar.

- Comece com "Assunto: " e uma linha curta que resuma o pedido.
- Depois, saudação, corpo em parágrafos curtos e fecho.
- Use o nome do destinatário somente se ele foi dito.
- Mantenha o pedido e os prazos exatamente como foram falados; não prometa nada
  que não foi prometido.
- Não invente assinatura: use o nome de quem ditou só se ele apareceu no texto;
  caso contrário, termine no fecho.
- Sem emojis.
"""

_WHATSAPP = """\
Transforme o ditado em uma mensagem de WhatsApp.

- Direta e conversacional, como se estivesse falando com a pessoa.
- Frases curtas; no máximo dois parágrafos.
- Sem saudação formal, sem "Prezado", sem assinatura, sem emojis.
- Preserve pedidos, prazos e valores ditos.
"""

_PROGRAMACAO = """\
Transforme o ditado em uma tarefa técnica para quem vai programar.

- Preserve nomes de funções, variáveis, arquivos, bibliotecas e frameworks
  exatamente como foram ditos.
- Organize em: contexto (1–2 linhas), o que fazer (passos numerados) e
  restrições, quando existirem.
- Separe correções de funcionalidades novas quando o texto deixar isso claro.
- Não invente requisitos, nomes de arquivo nem decisões técnicas.
- O que faltar para executar, liste no fim em "Pontos a esclarecer".
"""

_PROMPT_IA = """\
Transforme o ditado em instruções para um agente de IA executar.

- Escreva no imperativo, em passos ordenados.
- Diga o objetivo em uma linha, antes dos passos.
- Inclua o que deve ser evitado, se o texto disser.
- Não invente ferramentas, arquivos nem critérios de aceite.
- O que faltar, liste em "Pontos a esclarecer".
"""

_ACADEMICO = """\
Transforme o ditado em um trecho de texto acadêmico.

- Linguagem impessoal e formal, sem gírias e sem floreio.
- Preserve o raciocínio, os dados e as citações como foram ditos.
- Não acrescente referências, autores nem conclusões que não foram falados.
"""

_CURRICULO = """\
Organize o ditado como itens de currículo.

- Agrupe em Experiência, Competências e Formação — só as seções que o texto
  permitir.
- Use frases curtas, começando por verbo de ação, sem "eu".
- Preserve cargos, empresas, períodos e tecnologias exatamente como ditos.
- NÃO invente datas, empregadores, certificações nem resultados. O que não foi
  dito fica fora; se faltar um dado essencial, escreva [a esclarecer].
"""

_CARTA = """\
Transforme o ditado em uma carta pessoal.

- Preserve o tom afetivo e o jeito de falar de quem ditou.
- Estrutura de carta: saudação, corpo e despedida.
- Não formalize demais nem apague a pessoalidade.
- Não acrescente fatos, memórias nem sentimentos que não foram ditos.
"""

_ATA = """\
Transforme o ditado em uma ata de reunião.

- Estruture em: Assuntos tratados, Decisões e Encaminhamentos.
- Em cada encaminhamento, registre responsável e prazo **somente** se foram
  ditos; caso contrário, escreva [a definir].
- Preserve nomes, números e datas como foram falados.
- Não invente participantes nem decisões.
"""

BUILTIN_PROFILES: tuple[ProfileSpec, ...] = (
    ProfileSpec(
        slug=LITERAL_SLUG,
        name="Transcrição fiel",
        instructions="",
        hint=FORMAT_HINT,
    ),
    ProfileSpec(
        slug=REVISED_SLUG,
        name="Texto revisado",
        instructions=_REVISED,
        hint=FORMAT_HINT,
        options={"tom": "neutro", "concisao": "normal"},
    ),
    ProfileSpec(
        slug="email",
        name="E-mail profissional",
        instructions=_EMAIL,
        options={"tom": "formal", "concisao": "normal"},
    ),
    ProfileSpec(
        slug="whatsapp",
        name="WhatsApp",
        instructions=_WHATSAPP,
        options={"tom": "informal", "concisao": "curto"},
    ),
    ProfileSpec(
        slug="programacao",
        name="Tarefa de programação",
        instructions=_PROGRAMACAO,
        options={"preservar_termos": True},
    ),
    ProfileSpec(
        slug="prompt",
        name="Prompt para IA",
        instructions=_PROMPT_IA,
        options={"concisao": "detalhado"},
    ),
    ProfileSpec(
        slug="academico",
        name="Texto acadêmico",
        instructions=_ACADEMICO,
        options={"tom": "formal"},
    ),
    ProfileSpec(
        slug="curriculo",
        name="Currículo",
        instructions=_CURRICULO,
        options={"concisao": "curto"},
    ),
    ProfileSpec(
        slug="carta",
        name="Carta pessoal",
        instructions=_CARTA,
        options={"tom": "informal"},
    ),
    ProfileSpec(
        slug="ata",
        name="Ata de reunião",
        instructions=_ATA,
        options={"concisao": "detalhado"},
    ),
)

BUILTIN_BY_SLUG = {profile.slug: profile for profile in BUILTIN_PROFILES}

TOM_LABEL = {"formal": "formal", "neutro": "neutro", "informal": "informal"}
CONCISION_LABEL = {"curto": "curta", "normal": "normal", "detalhado": "detalhada"}


def compose_instructions(profile: ProfileSpec) -> str:
    """Regras comuns + o que o perfil faz + itens do usuário + estilo."""
    parts = [BASE_RULES.strip(), profile.instructions.strip()]
    options = profile.options or {}

    items = [str(item).strip() for item in options.get("items") or [] if str(item).strip()]
    if items:
        parts.append("Regras deste perfil:\n" + "\n".join(f"- {item}" for item in items))

    style: list[str] = []
    if options.get("tom") in TOM_LABEL:
        style.append(f"tom {TOM_LABEL[options['tom']]}")
    if options.get("concisao") in CONCISION_LABEL:
        style.append(f"concisão {CONCISION_LABEL[options['concisao']]}")
    if options.get("preservar_termos"):
        style.append("preserve termos técnicos como foram ditos")
    if style:
        parts.append("Ajustes de estilo: " + "; ".join(style) + ".")
    return "\n\n".join(part for part in parts if part)


def is_literal(slug: str | None) -> bool:
    return (slug or "").strip().lower() in {"", LITERAL_SLUG}


def is_pristine(spec: ProfileSpec) -> bool:
    """A semente do perfil não foi editada (instruções, dica e opções originais).

    O perfil "revisado" usa isto para só pular a segunda chamada quando ainda é
    o prompt de fábrica; se o usuário ajustou o texto, o ajuste sempre roda.
    """
    default = BUILTIN_BY_SLUG.get(spec.slug)
    if default is None or not spec.builtin:
        return False
    return (
        spec.instructions.strip() == default.instructions.strip()
        and (spec.hint or "") == (default.hint or "")
        and (spec.options or {}) == (default.options or {})
    )
