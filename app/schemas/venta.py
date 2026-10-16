"""Esquemas Pydantic para el módulo de Ventas.

Soporte multi-unidad: cada ítem acepta opcionalmente la cantidad física O el
importe a cobrar (para productos vendidos por peso, p. ej. "¿cuánto sale $150?").
El backend, si recibe `importe`, calcula la cantidad física exacta
(importe / precio unitario) y descuenta esa fracción del stock.
"""

from typing import List, Optional
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, model_validator


class VentaItem(BaseModel):
    """Ítem dentro de una venta (validation de entrada).

    Campos:
        producto_id : ID del producto (obligatorio).
        cantidad    : cantidad física/unidades. Opcional.
        importe     : importe ($) a cobrar. Alternativo a `cantidad`, pensado
                      para productos vendidos por peso.
        precio_unitario: opcional; si se omite se toma de la base de datos.
        descuento   : descuento total del ítem.

    Regla de negocio: debe venir `cantidad` o `importe`, pero no ambos.
    """

    producto_id: UUID = Field(..., description="ID del producto vendido")
    cantidad: Optional[Decimal] = Field(
        None,
        gt=0,
        le=999_999,
        description="Cantidad física (unidades o kg). Alternativo a importe.",
    )
    importe: Optional[Decimal] = Field(
        None,
        gt=0,
        le=999_999_999,
        description="Importe ($) a cobrar. Para venta por peso: se deriva la cantidad exacta.",
    )
    precio_unitario: Optional[Decimal] = Field(
        None, gt=0, le=999_999_999, description="Precio por unidad (si no se envía, se toma de la BD)"
    )
    descuento: Decimal = Field(
        Decimal("0"), ge=0, le=999_999_999, description="Descuento total del ítem"
    )

    @model_validator(mode="after")
    def _validar_cantidad_o_importe(self) -> "VentaItem":
        """Garantiza al menos uno, y no ambos, entre cantidad e importe."""
        tiene_cantidad = self.cantidad is not None
        tiene_importe = self.importe is not None
        if not tiene_cantidad and not tiene_importe:
            raise ValueError(
                "Cada ítem debe indicar 'cantidad' o 'importe' (al menos uno)."
            )
        if tiene_cantidad and tiene_importe:
            raise ValueError(
                "Indica 'cantidad' o 'importe', no ambos a la vez para un mismo ítem."
            )
        return self


class VentaCreate(BaseModel):
    """Esquema de entrada para registrar una venta."""

    items: List[VentaItem] = Field(
        ..., min_length=1, description="Lista de productos vendidos"
    )
    metodo_pago: str = Field(
        ...,
        pattern="^(efectivo|tarjeta|transferencia|mixto|cuenta_corriente)$",
        description="Método de pago de la venta",
    )
    cliente: str = Field("Mostrador", max_length=200, description="Nombre del cliente")
    # Sólo cuando metodo_pago == 'cuenta_corriente' (fiado).
    cliente_id: Optional[int] = Field(
        None, description="ID del cliente con cuenta corriente (fiado)"
    )
    paga_con: Optional[Decimal] = Field(None, description="Monto entregado por el cliente")
    vuelto: Optional[Decimal] = Field(None, description="Vuelto a entregar al cliente")

    @model_validator(mode="after")
    def validar_items(self) -> "VentaCreate":
        """Valida que no haya productos repetidos, la cuenta corriente y,
        en pagos en efectivo, que el monto abonado no sea menor al total.

        NOTA: el total definitivo se recalcula en el router contra los precios
        reales de la BD (defensa en profundidad). Aquí solo se valida que, si
        el cliente informa `paga_con` en efectivo, sea un monto positivo; la
        comparación contra el total autoritativo vive en `registrar_venta`.
        """
        ids = [item.producto_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("No se pueden repetir productos en una misma venta.")

        if self.metodo_pago == "cuenta_corriente" and not self.cliente_id:
            raise ValueError(
                "Para ventas a cuenta corriente (fiado) es obligatorio indicar "
                "el cliente (cliente_id)."
            )

        # Monto abonado: si se informa (efectivo), debe ser estrictamente > 0.
        if self.metodo_pago == "efectivo" and self.paga_con is not None:
            if Decimal(self.paga_con) <= 0:
                raise ValueError(
                    "El monto ingresado no puede ser menor al total a pagar."
                )
        return self


class VentaOut(BaseModel):
    """Esquema de respuesta de una venta registrada."""

    id: UUID
    folio: str
    fecha: datetime
    total: Decimal
    metodo_pago: str
    cliente: str
    estado: str = "activa"
    anulada_en: Optional[datetime] = None
    anulada_por: Optional[str] = None
    motivo_anulacion: Optional[str] = None
    paga_con: Optional[Decimal] = None
    vuelto: Optional[Decimal] = None
    creado_en: datetime

    model_config = ConfigDict(from_attributes=True)


class VentaItemOut(BaseModel):
    """Ítem de detalle dentro de una venta (respuesta)."""

    id: UUID
    producto_id: UUID
    # Decimal: puede representar kg fraccionales para productos por peso.
    cantidad: Decimal
    precio_unitario: Decimal
    descuento: Decimal

    model_config = ConfigDict(from_attributes=True)


class VentaDetalleOut(VentaOut):
    """Respuesta de una venta incluyendo sus ítems y métodos de pago."""

    items: List[VentaItemOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class VentaItemHistorialOut(VentaItemOut):
    """Ítem dentro del historial de ventas (incluye nombre de producto y subtotal).

    Pensado para el módulo anillo de Ventas (ventas.html), donde se quiere
    mostrar en cada ticket qué productos se vendieron sin resolver el nombre
    del producto en el cliente.
    """

    nombre_producto: str
    subtotal: Decimal  # (precio_unitario * cantidad) - descuento

    model_config = ConfigDict(from_attributes=True)


class VentaHistorialOut(VentaOut):
    """Cabecera de venta con sus ítems enriquecidos para el reporte por fechas."""

    items: List[VentaItemHistorialOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class AnulacionOut(BaseModel):
    """Respuesta de la anulación de una venta.

    Incluye los folios y montos afectados (venta y, si aplica, el abono
    revertido de la cuenta corriente) para trazabilidad del cajero.
    """

    venta_id: UUID
    folio: str
    estado: str
    total_revertido: Decimal
    stock_devuelto: int
    saldo_cc_ajustado: Optional[Decimal] = None
    mensaje: str


class AnularVentaIn(BaseModel):
    motivo: str = Field(..., max_length=255)
    password: str

