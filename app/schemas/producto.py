"""Esquemas Pydantic para el módulo de Productos."""

from typing import Optional
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict

from app.models import Producto

# Unidades de venta soportadas. FUENTE ÚNICA: se derivan de `Producto` para que
# modelo ORM y validación Pydantic no puedan divergir (DRY).
TIPOS_UNIDAD = Producto.TIPOS_UNIDAD
_PATTERN_TIPO_UNIDAD = "^(" + "|".join(Producto.TIPOS_UNIDAD) + ")$"


class ProductoBase(BaseModel):
    """Campos base de un producto."""

    nombre: str = Field(
        ..., min_length=1, max_length=200, description="Nombre del producto"
    )
    descripcion: Optional[str] = Field(
        None, max_length=500, description="Descripción opcional"
    )
    codigo_barras: Optional[str] = Field(
        None, max_length=50, description="Código de barras / SKU"
    )
    precio: Decimal = Field(..., gt=0, description="Precio de venta")
    costo: Optional[Decimal] = Field(None, ge=0, description="Costo unitario")
    porcentaje_ganancia: Optional[Decimal] = Field(
        None, ge=0, le=1000, description="Margen de ganancia objetivo (%)"
    )
    # Decimal (no int) para que en 'peso' el stock admita fracciones de kg.
    stock: Decimal = Field(Decimal("0"), ge=0, description="Cantidad en stock")
    stock_minimo: Decimal = Field(
        Decimal("0"), ge=0, description="Stock mínimo para alerta"
    )
    categoria: Optional[str] = Field(
        None, max_length=100, description="Categoría del producto"
    )
    # Campos multi-rubro (opcionales; el POS los ignora si no aplican).
    marca: Optional[str] = Field(
        None, max_length=80, description="Marca (indumentaria)"
    )
    talle: Optional[str] = Field(
        None, max_length=40, description="Talle (indumentaria)"
    )
    color: Optional[str] = Field(
        None, max_length=40, description="Color (indumentaria)"
    )
    fecha_vencimiento: Optional[datetime] = Field(
        None, description="Fecha de vencimiento (perecibles)"
    )
    # --- Variantes de impresión (librería: productos tipo 'servicio') ---
    # Aplican SOLO cuando tipo_unidad == 'servicio' (copia/impresión). Nullable:
    # el resto de rubros/productos las ignoran. Columnas dedicadas (semántica
    # limpia en vez de reutilizar talle/color — ver Producto en app.models).
    tipo_papel: Optional[str] = Field(
        None, max_length=40, description="Tipo de papel (librería/servicio)"
    )
    color_bn: Optional[str] = Field(
        None, max_length=20, description="Color o B/N (librería/servicio)"
    )
    tipo_unidad: str = Field(
        "unidad",
        pattern=_PATTERN_TIPO_UNIDAD,
        description=(
            "Unidad de venta: peso | unidad | porcion | metros | litros | servicio"
        ),
    )
    activo: bool = Field(True, description="Si el producto está activo para la venta")


class ProductoCreate(ProductoBase):
    """Esquema para crear un nuevo producto."""


class ProductoUpdate(BaseModel):
    """Esquema para actualizar un producto (todos los campos opcionales)."""

    nombre: Optional[str] = Field(None, min_length=1, max_length=200)
    descripcion: Optional[str] = Field(None, max_length=500)
    codigo_barras: Optional[str] = Field(None, max_length=50)
    precio: Optional[Decimal] = Field(None, gt=0)
    costo: Optional[Decimal] = Field(None, ge=0)
    porcentaje_ganancia: Optional[Decimal] = Field(None, ge=0, le=1000)
    stock: Optional[Decimal] = Field(None, ge=0)
    stock_minimo: Optional[Decimal] = Field(None, ge=0)
    categoria: Optional[str] = Field(None, max_length=100)
    marca: Optional[str] = Field(None, max_length=80)
    talle: Optional[str] = Field(None, max_length=40)
    color: Optional[str] = Field(None, max_length=40)
    fecha_vencimiento: Optional[datetime] = Field(None)
    tipo_papel: Optional[str] = Field(None, max_length=40)
    color_bn: Optional[str] = Field(None, max_length=20)
    tipo_unidad: Optional[str] = Field(
        None, pattern=_PATTERN_TIPO_UNIDAD, description="Unidad de venta"
    )
    activo: Optional[bool] = None


class ProductoOut(ProductoBase):
    """Esquema de respuesta completo de un producto."""

    id: UUID
    creado_en: datetime
    actualizado_en: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
