"""Esquemas Pydantic para el módulo de Arqueo de Caja."""

from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


# ============================================================
# Esquemas de entrada (request)
# ============================================================
class ArqueoApertura(BaseModel):
    """Cuerpo para abrir la caja registradora.

    Se registra el monto inicial en efectivo con el que arranca el turno.
    """

    monto_inicial: Decimal = Field(
        Decimal("0"),
        ge=0,
        description="Fondo de caja inicial en efectivo",
    )
    observaciones: Optional[str] = Field(
        None,
        max_length=300,
        description="Notas opcionales de apertura",
    )


class IngresoEgresoCreate(BaseModel):
    """Cuerpo para registrar un movimiento manual de dinero durante el turno.

    - `ingreso`: dinero que entra a la caja (p. ej. reposición de cambio).
    - `egreso`:  dinero que sale de la caja (p. ej. pago a proveedor, gasto).
    """

    tipo: str = Field(
        ...,
        pattern="^(ingreso|egreso)$",
        description="Tipo de movimiento: ingreso | egreso",
    )
    monto: Decimal = Field(..., gt=0, description="Monto del movimiento (> 0)")
    concepto: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Motivo o descripción del movimiento",
    )
    metodo_pago: str = Field(
        "efectivo",
        pattern="^(efectivo|tarjeta|transferencia|otro)$",
        description="Método de pago asociado al movimiento",
    )


class ArqueoCierre(BaseModel):
    """Cuerpo para cerrar la caja.

    El usuario ingresa el `monto_final`: el total en efectivo contado
    físicamente al cerrar el turno. El sistema calcula el total esperado
    (monto inicial + ventas en efectivo + ingresos - egresos) y la diferencia.
    """

    monto_final: Decimal = Field(
        ...,
        ge=0,
        description="Dinero real en efectivo contado en caja al cierre",
    )
    observaciones: Optional[str] = Field(
        None,
        max_length=300,
        description="Notas opcionales de cierre",
    )


# ============================================================
# Esquemas de respuesta (response)
# ============================================================
class MovimientoOut(BaseModel):
    """Esquema de respuesta de un movimiento de caja."""

    id: UUID
    tipo: str
    monto: Decimal
    concepto: str
    metodo_pago: str
    fecha: datetime

    model_config = ConfigDict(from_attributes=True)


class ArqueoOut(BaseModel):
    """Esquema de respuesta de un arqueo de caja."""

    id: UUID
    fecha_apertura: datetime
    monto_inicial: Decimal
    fecha_cierre: Optional[datetime] = None
    monto_esperado: Optional[Decimal] = None
    monto_real: Optional[Decimal] = None
    monto_final: Optional[Decimal] = None
    diferencia: Optional[Decimal] = None
    estado: str  # abierto | cerrado
    observaciones_apertura: Optional[str] = None
    observaciones_cierre: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CierreOut(BaseModel):
    """Esquema de respuesta detallado del cierre de caja.

    Incluye el desglose del cálculo para trazabilidad y auditoría.
    """

    arqueo_id: UUID
    fecha_apertura: datetime
    fecha_cierre: datetime
    monto_inicial: Decimal
    ventas_efectivo: Decimal
    ventas_tarjeta: Decimal = Decimal("0")
    ventas_transferencia: Decimal = Decimal("0")
    ventas_mixto: Decimal = Decimal("0")
    # Ventas a cuenta corriente (fiado): informativa. NO suma al físico esperado.
    ventas_credito: Decimal = Decimal("0")
    otros_medios: Decimal = Decimal("0")
    ingresos_manuales: Decimal
    egresos_manuales: Decimal
    total_esperado: Decimal
    monto_final: Decimal
    diferencia: Decimal
    observaciones: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
