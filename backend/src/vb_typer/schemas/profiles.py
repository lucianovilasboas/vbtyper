"""Esquemas dos perfis de texto."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProfileRead(BaseModel):
    slug: str
    name: str
    instructions: str
    hint: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    builtin: bool


class ProfileCreate(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    instructions: str = Field(min_length=10, max_length=8000)
    hint: str | None = Field(default=None, max_length=500)
    options: dict[str, Any] = Field(default_factory=dict)


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=60)
    instructions: str | None = Field(default=None, min_length=10, max_length=8000)
    hint: str | None = Field(default=None, max_length=500)
    options: dict[str, Any] | None = None
