"""Esquemas Pydantic para la configuración del negocio.

Representa el *singleton* de configuración del comercio (nombre, y a futuro
dirección/RUT/teléfono). El backend garantiza que solo existe una fila.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConfiguracionOut(BaseModel):
    """Configuración del negocio devuelta al frontend."""

    model_config = ConfigDict(from_attributes=True)

    nombre: str = ""
    actualizado_en: Optional[datetime] = None


class ConfiguracionUpdate(BaseModel):
    """Payload para actualizar la configuración del negocio.

    Solo se actualizan los campos provistos (patch parcial implícito: al ser
    un único campo, el comportamiento es idempotente y seguro).
    """

    nombre: str = Field(
        ...,
        max_length=200,
        description="Nombre del comercio impreso en los tickets.",
    )

    @field_validator("nombre")
    @classmethod
    def _limpiar_nombre(cls, v: str) -> str:
        """Normaliza espacios y rechaza cadenas vacías/solo-espacios."""
        v = (v or "").strip()
        if not v:
            raise ValueError("El nombre del negocio no puede estar vacío.")
        return v
