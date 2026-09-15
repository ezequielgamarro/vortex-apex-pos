"""Esquemas Pydantic para el módulo de Reportes / Dashboard analítico.

Modelan la respuesta de `GET /api/reportes/dashboard`, pensada para alimentar
los gráficos (Chart.js): serie temporal de ventas, top de productos y
distribución de ingresos por método de pago.

Nota sobre dinero: los montos se transportan como Decimal (serializado por
FastAPI como número con precisión controlada por Pydantic); el cliente los
formatea con Intl.NumberFormat. Se evita float explícito en la capa de modelo
para no perder precisión monetaria antes de la serialización.
"""

from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class PuntoSerie(BaseModel):
    """Un punto de la serie temporal de ventas (un día o un mes)."""

    periodo: str = Field(..., description="Etiqueta del periodo: 'YYYY-MM-DD' o 'YYYY-MM'.")
    total: Decimal = Field(..., description="Suma de importes vendidos en el periodo.")
    cantidad: int = Field(..., description="Número de ventas en el periodo.")


class ProductoVendido(BaseModel):
    """Fila del top de productos más vendidos (por cantidad)."""

    producto_id: str = Field(..., description="UUID del producto.")
    nombre: str = Field(..., description="Nombre del producto (o 'Producto eliminado').")
    cantidad: Decimal = Field(..., description="Cantidad total vendida (admite kg fraccional).")
    importe: Decimal = Field(..., description="Importe total vendido del producto.")


class MetodoPagoDistribucion(BaseModel):
    """Un segmento de la distribución de ingresos por método de pago."""

    metodo_pago: str = Field(
        ...,
        description="efectivo | tarjeta | transferencia | mixto | cuenta_corriente.",
    )
    total: Decimal = Field(..., description="Importe total cobrado por ese método.")
    cantidad: int = Field(..., description="Número de ventas por ese método.")


class UltimoArqueoOut(BaseModel):
    """Resumen del último arqueo cerrado (compatibilidad dashboard legacy)."""

    id: str
    diferencia: Optional[Decimal] = None


class DashboardKpisOut(BaseModel):
    """KPIs generales (compatibilidad con el dashboard legacy de inventario)."""

    total_productos: int
    productos_bajo_stock: int
    ventas_hoy: Decimal
    ultimo_arqueo: Optional[UltimoArqueoOut] = None


class DashboardOut(BaseModel):
    """Respuesta completa de `GET /api/reportes/dashboard`.

    Es un SUPERSET retrocompatible: además de las series analíticas, conserva
    los KPIs del dashboard anterior (bloque `kpis`) para no romper consumidores.
    """

    agrupacion: str = Field(..., description="'dias' | 'meses'.")
    rango: int = Field(..., description="Cantidad de periodos devueltos.")

    serie_ventas: List[PuntoSerie] = Field(default_factory=list)
    top_productos: List[ProductoVendido] = Field(default_factory=list)
    por_metodo_pago: List[MetodoPagoDistribucion] = Field(default_factory=list)

    # Totales globales del periodo consultado (útil para tarjetas KPI).
    ventas_totales: Decimal = Field(Decimal("0"))
    cantidad_ventas: int = Field(0)

    # Bloque legacy (KPIs de inventario) — se mantiene por compatibilidad.
    kpis: Optional[DashboardKpisOut] = None
