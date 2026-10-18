"""Esquemas de resposta comuns."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict


def _to_iso(value: Any) -> Any:
    if isinstance(value, str) and len(value) == 19 and value[10] == " ":
        return value.replace(" ", "T", 1)
    return value


IsoStamp = Annotated[str, BeforeValidator(_to_iso)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
