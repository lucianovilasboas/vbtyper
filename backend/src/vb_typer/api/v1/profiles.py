"""Perfis de texto: embutidos (somente leitura) e personalizados."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from vb_typer.api.deps import ContainerDep
from vb_typer.domain.profiles import ProfileSpec
from vb_typer.schemas.profiles import ProfileCreate, ProfileRead, ProfileUpdate

router = APIRouter(prefix="/profiles", tags=["perfis"])


def _read(spec: ProfileSpec) -> ProfileRead:
    return ProfileRead(
        slug=spec.slug,
        name=spec.name,
        instructions=spec.instructions,
        hint=spec.hint,
        options=dict(spec.options or {}),
        builtin=spec.builtin,
    )


@router.get("", response_model=list[ProfileRead])
def list_profiles(container: ContainerDep) -> list[ProfileRead]:
    return [_read(spec) for spec in container.profiles.list()]


@router.post("", response_model=ProfileRead, status_code=status.HTTP_201_CREATED)
def create_profile(payload: ProfileCreate, container: ContainerDep) -> ProfileRead:
    spec = container.profiles.create(
        name=payload.name,
        instructions=payload.instructions,
        hint=payload.hint,
        options=payload.options,
    )
    return _read(spec)


@router.patch("/{slug}", response_model=ProfileRead)
def update_profile(slug: str, payload: ProfileUpdate, container: ContainerDep) -> ProfileRead:
    spec = container.profiles.update(
        slug,
        name=payload.name,
        instructions=payload.instructions,
        hint=payload.hint,
        options=payload.options,
    )
    return _read(spec)


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(slug: str, container: ContainerDep) -> Response:
    container.profiles.delete(slug)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
