"""Perfis de texto: todos vivem no banco, semeados uma vez a partir do código.

Os padrões são inseridos na primeira inicialização (`seed_defaults`) e a partir
daí são perfis como qualquer outro: editáveis e removíveis. A única exceção é a
transcrição fiel, que é a base do ditado e não pode ser removida (só renomeada).
O marcador `app_settings.profiles_seeded` garante que apagar um padrão não o
ressuscita na próxima inicialização.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from sqlalchemy import insert
from sqlalchemy.orm import Session, sessionmaker

from vb_typer.core.timeutil import local_stamp
from vb_typer.db.models import AppSetting, Profile
from vb_typer.domain.errors import ConflictError, DomainError, NotFoundError
from vb_typer.domain.profiles import BUILTIN_PROFILES, LITERAL_SLUG, ProfileSpec
from vb_typer.repositories.profiles import ProfileRepository

ALLOWED_TONES = ("formal", "neutro", "informal")
ALLOWED_CONCISION = ("curto", "normal", "detalhado")
NAME_MIN, NAME_MAX = 2, 60
INSTRUCTIONS_MIN, INSTRUCTIONS_MAX = 10, 8000
HINT_MAX = 500
MAX_ITEMS = 12
ITEM_MIN, ITEM_MAX = 3, 200


def _slugify(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug or "perfil")[:40]


def _clean_options(options: dict[str, Any] | None, allowed_models: tuple[str, ...]) -> dict:
    """Guarda só as chaves conhecidas, com valores válidos.

    - ``tom``/``concisao``/``preservar_termos``: ajustes de estilo;
    - ``items``: regras curtas escritas pelo usuário, viram um bloco no prompt;
    - ``modelo``: modelo de texto só deste perfil (vazio = o padrão global).
    """
    cleaned: dict[str, Any] = {}
    if not isinstance(options, dict):
        return cleaned
    tone = str(options.get("tom") or "").strip().lower()
    if tone in ALLOWED_TONES:
        cleaned["tom"] = tone
    concision = str(options.get("concisao") or "").strip().lower()
    if concision in ALLOWED_CONCISION:
        cleaned["concisao"] = concision
    if options.get("preservar_termos") is True:
        cleaned["preservar_termos"] = True
    # Ditado contínuo: usa os ditados anteriores como contexto da segunda chamada.
    if options.get("continuo") is True:
        cleaned["continuo"] = True

    raw_items = options.get("items")
    if isinstance(raw_items, list):
        items = [str(item).strip() for item in raw_items]
        items = [item for item in items if item]
        if len(items) > MAX_ITEMS:
            raise DomainError(f"No máximo {MAX_ITEMS} itens por perfil.", code="too_many_items")
        for item in items:
            if not ITEM_MIN <= len(item) <= ITEM_MAX:
                raise DomainError(
                    f"Cada item deve ter entre {ITEM_MIN} e {ITEM_MAX} caracteres.",
                    code="invalid_item",
                )
        if items:
            cleaned["items"] = items

    model = str(options.get("modelo") or "").strip()
    if model:
        if model not in allowed_models:
            raise DomainError(
                "Modelo de texto inválido. Use um de: " + ", ".join(allowed_models) + ".",
                code="invalid_smart_model",
            )
        cleaned["modelo"] = model
    return cleaned


def _to_spec(row: Profile) -> ProfileSpec:
    options = dict(row.options or {})
    return ProfileSpec(
        slug=row.slug,
        name=row.name,
        instructions=row.instructions,
        hint=row.hint,
        options=options,
        builtin=bool(row.seeded),
        model=options.get("modelo"),
    )


class ProfileService:
    def __init__(self, session_factory: sessionmaker[Session], settings) -> None:
        self.session_factory = session_factory
        self.allowed_models = tuple(settings.allowed_smart_models)
        self.repo = ProfileRepository()

    # --- leitura -----------------------------------------------------------
    def seed_defaults(self) -> None:
        """Insere os perfis padrão uma única vez; nunca ressuscita os apagados.

        Chamado na inicialização, depois de `settings.current()` garantir a linha
        de `app_settings`. O marcador é gravado na mesma transação da semente.
        """
        with self.session_factory() as session:
            state = session.get(AppSetting, 1)
            if state is None:
                raise RuntimeError("app_settings precisa existir antes da semente dos perfis.")
            if state.profiles_seeded:
                return
            now = local_stamp()
            for order, spec in enumerate(BUILTIN_PROFILES):
                session.execute(
                    insert(Profile)
                    .values(
                        slug=spec.slug,
                        name=spec.name,
                        instructions=spec.instructions,
                        hint=spec.hint,
                        options=dict(spec.options or {}),
                        seeded=True,
                        sort_order=order,
                        created_at=now,
                        updated_at=now,
                    )
                    .prefix_with("OR IGNORE")
                )
            state.profiles_seeded = True
            state.updated_at = now
            session.commit()

    def list(self) -> list[ProfileSpec]:
        with self.session_factory() as session:
            return [_to_spec(row) for row in self.repo.list(session)]

    def get(self, slug: str) -> ProfileSpec:
        normalized = (slug or "").strip().lower()
        with self.session_factory() as session:
            row = self.repo.get(session, normalized)
            if row is None:
                raise NotFoundError(f"Perfil '{slug}' não existe.")
            return _to_spec(row)

    def exists(self, slug: str) -> bool:
        normalized = (slug or "").strip().lower()
        with self.session_factory() as session:
            return self.repo.get(session, normalized) is not None

    # --- escrita -----------------------------------------------------------
    def create(
        self,
        *,
        name: str,
        instructions: str,
        hint: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> ProfileSpec:
        clean_name = (name or "").strip()
        clean_instructions = (instructions or "").strip()
        self._validate(clean_name, clean_instructions)
        clean_hint = (hint or "").strip()
        if len(clean_hint) > HINT_MAX:
            raise DomainError(f"A dica deve ter até {HINT_MAX} caracteres.", code="invalid_hint")

        with self.session_factory() as session:
            slug = self._unique_slug(session, _slugify(clean_name))
            row = Profile(
                slug=slug,
                name=clean_name,
                instructions=clean_instructions,
                hint=clean_hint or None,
                options=_clean_options(options, self.allowed_models),
                seeded=False,
                sort_order=0,
                created_at=local_stamp(),
                updated_at=local_stamp(),
            )
            self.repo.add(session, row)
            session.commit()
            session.refresh(row)
            return _to_spec(row)

    def update(
        self,
        slug: str,
        *,
        name: str | None = None,
        instructions: str | None = None,
        hint: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> ProfileSpec:
        normalized = (slug or "").strip().lower()
        with self.session_factory() as session:
            row = self.repo.get(session, normalized)
            if row is None:
                raise NotFoundError(f"Perfil '{slug}' não existe.")
            if normalized == LITERAL_SLUG:
                # A transcrição fiel não tem instruções: só o nome faz sentido.
                if name is not None:
                    new_name = name.strip()
                    if not NAME_MIN <= len(new_name) <= NAME_MAX:
                        raise DomainError(
                            f"O nome deve ter entre {NAME_MIN} e {NAME_MAX} caracteres.",
                            code="invalid_name",
                        )
                    row.name = new_name
                row.updated_at = local_stamp()
                session.commit()
                session.refresh(row)
                return _to_spec(row)
            new_name = row.name if name is None else name.strip()
            new_instructions = row.instructions if instructions is None else instructions.strip()
            self._validate(new_name, new_instructions)
            row.name = new_name
            row.instructions = new_instructions
            if hint is not None:
                clean_hint = hint.strip()
                if len(clean_hint) > HINT_MAX:
                    raise DomainError(
                        f"A dica deve ter até {HINT_MAX} caracteres.", code="invalid_hint"
                    )
                row.hint = clean_hint or None
            if options is not None:
                row.options = _clean_options(options, self.allowed_models)
            row.updated_at = local_stamp()
            session.commit()
            session.refresh(row)
            return _to_spec(row)

    def delete(self, slug: str) -> None:
        normalized = (slug or "").strip().lower()
        if normalized == LITERAL_SLUG:
            raise ConflictError("A transcrição fiel é a base do ditado e não pode ser removida.")
        with self.session_factory() as session:
            row = self.repo.get(session, normalized)
            if row is None:
                raise NotFoundError(f"Perfil '{slug}' não existe.")
            self.repo.delete(session, row)
            state = session.get(AppSetting, 1)
            if state is not None and state.default_profile == normalized:
                # Nunca deixar o padrão apontando para um perfil que sumiu.
                state.default_profile = LITERAL_SLUG
                state.mode = "literal"
                state.updated_at = local_stamp()
            session.commit()

    # --- internos ----------------------------------------------------------
    @staticmethod
    def _validate(name: str, instructions: str) -> None:
        if not NAME_MIN <= len(name) <= NAME_MAX:
            raise DomainError(
                f"O nome deve ter entre {NAME_MIN} e {NAME_MAX} caracteres.", code="invalid_name"
            )
        if not INSTRUCTIONS_MIN <= len(instructions) <= INSTRUCTIONS_MAX:
            raise DomainError(
                "As instruções devem ter entre "
                f"{INSTRUCTIONS_MIN} e {INSTRUCTIONS_MAX} caracteres.",
                code="invalid_instructions",
            )

    def _unique_slug(self, session: Session, base: str) -> str:
        candidate = base
        counter = 2
        while self.repo.get(session, candidate) is not None:
            suffix = f"-{counter}"
            candidate = f"{base[: 40 - len(suffix)]}{suffix}"
            counter += 1
        return candidate
