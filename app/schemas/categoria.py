"""Esquemas Pydantic para Categorías."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class CategoriaBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)


class CategoriaCreate(CategoriaBase):
    """Creación de categoría por nombre (si ya existe se retorna la existente)."""


class CategoriaOut(CategoriaBase):
    id: int
    creado_en: datetime

    model_config = ConfigDict(from_attributes=True)
