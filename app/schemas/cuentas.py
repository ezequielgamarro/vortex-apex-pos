"""Esquemas Pydantic para Cuentas Corrientes (fiado a clientes)."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class ClienteBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=200)
    telefono: Optional[str] = Field(None, max_length=60)


class ClienteCreate(ClienteBase):
    """Creación de cliente. Saldo inicial siempre 0."""


class ClienteOut(ClienteBase):
    id: int
    saldo_deuda: Decimal = Field(default=Decimal("0"))
    activo: bool = True
    creado_en: datetime

    model_config = ConfigDict(from_attributes=True)


class MovimientoCuentaOut(BaseModel):
    """Movimiento de cuenta corriente (cargo/abono)."""

    id: int
    cliente_id: int
    fecha: datetime
    tipo: str  # 'cargo' | 'abono'
    monto: Decimal
    venta_id: Optional[UUID] = None
    concepto: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DetalleClienteOut(ClienteOut):
    """Cliente con el historial de movimientos (cuenta corriente)."""

    movimientos: List[MovimientoCuentaOut] = Field(default_factory=list)


class AbonoCreate(BaseModel):
    """Abono de un cliente (reduce deuda; el dinero ingresa a la caja activa).

    El `cliente_id` NUNCA viaja en el body: viene por el path de la ruta
    (`POST /clientes/{cliente_id}/abonos`), evitando duplicar/desincronizar
    la referencia. Así el frontend envía sólo { monto, concepto }.
    """

    monto: Decimal = Field(..., gt=0, description="Monto del abono/pago")
    concepto: Optional[str] = Field(None, max_length=300)
