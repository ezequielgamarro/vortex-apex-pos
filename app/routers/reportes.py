"""Router de reportes agregaciones y KPIs para el dashboard.

Persistencia local vía SQLAlchemy + SQLite con `db: Session = Depends(get_db)`.
Genera: ventas por periodo, productos más vendidos y resumen de KPIs.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import requiere_rol, UsuarioActual
from app.models import Venta, VentaItem, Producto, Arqueo
from app.schemas.reporte import (
    DashboardOut,
    DashboardKpisOut,
    UltimoArqueoOut,
    PuntoSerie,
    ProductoVendido,
    MetodoPagoDistribucion,
)

# Todos los endpoints de este router son SOLO para administradores.
# Se aplica como dependencia a nivel de router para garantizar RBAC uniforme:
# cualquier ruta nueva hereda automáticamente la restricción (defensa en
# profundidad junto al filtrado del menú y RUTAS_SOLO_ADMIN del guard.js).
router = APIRouter(
    prefix="/reportes",
    tags=["Reportes"],
    dependencies=[Depends(requiere_rol("admin"))],
)

# Cuántos periodos devolver según la agrupación solicitada.
#   dias  -> últimos N días (7 por defecto; permite 30).
#   meses -> últimos N meses (6 por defecto; permite 12).
_RANGO_DIAS_DEFAULT = 7
_RANGO_MESES_DEFAULT = 6


def _desde_dt(desde: date) -> datetime:
    """Límite inferior (inicio del día) de un rango de fechas."""
    return datetime.combine(desde, datetime.min.time())


def _hasta_dt(hasta: date) -> datetime:
    """Límite superior (fin del día) de un rango de fechas."""
    return datetime.combine(hasta, datetime.max.time())


def _rango_dias(n: int) -> List[str]:
    """Lista de claves 'YYYY-MM-DD' de los últimos n días (incluye hoy)."""
    hoy = date.today()
    return [
        (hoy - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n - 1, -1, -1)
    ]


def _rango_meses(n: int) -> List[str]:
    """Lista de claves 'YYYY-MM' de los últimos n meses (incluye el actual)."""
    hoy = date.today()
    claves: List[str] = []
    y, m = hoy.year, hoy.month
    for _ in range(n):
        claves.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(claves))


@router.get("/ventas", summary="Resumen de ventas por periodo")
def resumen_ventas(
    fecha_desde: date,
    fecha_hasta: date,
    usuario: UsuarioActual = Depends(requiere_rol("admin")),
    db: Session = Depends(get_db),
):
    """Devuelve total, cantidad de ventas y desglose por método de pago del periodo."""
    try:
        ventas = (
            db.query(Venta)
            .filter(Venta.fecha >= _desde_dt(fecha_desde))
            .filter(Venta.fecha <= _hasta_dt(fecha_hasta))
            .all()
        )

        total = sum((Decimal(v.total) for v in ventas), Decimal("0"))
        por_metodo: dict[str, Decimal] = {}
        for v in ventas:
            por_metodo[v.metodo_pago] = por_metodo.get(
                v.metodo_pago, Decimal("0")
            ) + Decimal(v.total)

        return {
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            "total_vendido": total,
            "cantidad_ventas": len(ventas),
            "por_metodo_pago": {k: v for k, v in por_metodo.items()},
        }
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al consultar resumen de ventas: {str(exc)}",
        )


@router.get("/mas-vendidos", summary="Productos más vendidos del periodo")
def productos_mas_vendidos(
    fecha_desde: date,
    fecha_hasta: date,
    limite: int = 10,
    usuario: UsuarioActual = Depends(requiere_rol("admin")),
    db: Session = Depends(get_db),
):
    """Devuelve el ranking de productos más vendidos por cantidad en el periodo.

    La agregación (SUM cantidad e importe por producto, dentro de las ventas del
    rango) se resuelve en SQL vía una subconsulta contra `venta_items`, evitando
    traer filas innecesarias a Python.
    """
    try:
        limite = max(1, min(limite, 50))

        # Subconsulta: ids de ventas dentro del periodo.
        ventas_subq = (
            db.query(Venta.id)
            .filter(Venta.fecha >= _desde_dt(fecha_desde))
            .filter(Venta.fecha <= _hasta_dt(fecha_hasta))
            .subquery()
        )

        ranking_rows = (
            db.query(
                VentaItem.producto_id,
                func.sum(VentaItem.cantidad).label("cantidad_total"),
                func.sum(
                    VentaItem.cantidad * VentaItem.precio_unitario - VentaItem.descuento
                ).label("importe_total"),
            )
            .filter(VentaItem.venta_id.in_(db.query(ventas_subq.c.id)))
            .group_by(VentaItem.producto_id)
            .order_by(func.sum(VentaItem.cantidad).desc())
            .limit(limite)
            .all()
        )

        resultado = []
        for pid, cantidad_total, importe_total in ranking_rows:
            nombre = "Producto eliminado"
            prod = db.query(Producto).filter(Producto.id == pid).first()
            if prod is not None:
                nombre = prod.nombre
            resultado.append(
                {
                    "producto_id": pid,
                    "nombre": nombre,
                    # Decimal: la suma puede incluir fracciones (venta por peso).
                    "cantidad_total": Decimal(cantidad_total),
                    "importe_total": Decimal(importe_total),
                }
            )
        return resultado
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al consultar más vendidos: {str(exc)}",
        )


@router.get(
    "/dashboard",
    response_model=DashboardOut,
    summary="Dashboard analítico (series, top productos, métodos de pago)",
)
def dashboard(
    agrupacion: str = Query(
        "dias",
        pattern="^(dias|meses)$",
        description="'dias' (últimos N días) o 'meses' (últimos N meses).",
    ),
    rango: int = Query(
        0,
        ge=0,
        le=30,
        description=(
            "Cantidad de periodos. Si es 0, se usa el default por agrupación "
            "(dias=7, meses=6)."
        ),
    ),
    usuario: UsuarioActual = Depends(requiere_rol("admin")),
    db: Session = Depends(get_db),
):
    """Dashboard de analítica de negocio (SOLO admin).

    Devuelve, para el periodo consultado:
      a) Serie temporal de ventas (por día o por mes).
      b) Top 5 productos más vendidos por cantidad.
      c) Distribución de ingresos por método de pago.
      + KPIs legacy de inventario (compatibilidad).

    Parámetros:
      ?agrupacion=dias|meses   Ventana de agrupación.
      ?rango=N                 Cantidad de periodos (0 = default por agrupación).

    La agregación se resuelve en SQL (GROUP BY + func.sum + strftime) para no
    traer todas las ventas a Python: O(periodos) filas en lugar de O(ventas).
    """
    try:
        # 1) Normalizar el rango según la agrupación.
        es_meses = agrupacion == "meses"
        default_rango = _RANGO_MESES_DEFAULT if es_meses else _RANGO_DIAS_DEFAULT
        n = rango if rango > 0 else default_rango
        # Límite superior técnico coherente con el patrón `le=30` del Query.
        n = max(1, min(n, 30))

        # 2) Claves de periodo esperadas y cota inferior de fecha.
        if es_meses:
            claves = _rango_meses(n)
            clave_expr = func.strftime("%Y-%m", Venta.fecha)
        else:
            claves = _rango_dias(n)
            clave_expr = func.strftime("%Y-%m-%d", Venta.fecha)

        # Cota inferior como datetime naive (mismo criterio UTC naive del modelo).
        hoy = date.today()
        if es_meses:
            # Primer día del mes más antiguo del rango.
            y, m = hoy.year, hoy.month
            offset = n - 1
            m -= offset
            while m <= 0:
                m += 12
                y -= 1
            desde = datetime(y, m, 1, 0, 0, 0)
        else:
            desde = _desde_dt(hoy - timedelta(days=n - 1))

        # 3) (a) Serie temporal: agrupada en SQL por día/mes.
        filas = (
            db.query(
                clave_expr.label("periodo"),
                func.sum(Venta.total).label("total"),
                func.count(Venta.id).label("cantidad"),
            )
            .filter(Venta.fecha >= desde)
            .group_by(clave_expr)
            .all()
        )
        por_periodo = {p: (Decimal(t or 0), int(c or 0)) for (p, t, c) in filas}
        serie_ventas = [
            PuntoSerie(
                periodo=p,
                total=por_periodo.get(p, (Decimal("0"), 0))[0],
                cantidad=por_periodo.get(p, (Decimal("0"), 0))[1],
            )
            for p in claves
        ]

        # Totales globales del periodo consultado.
        ventas_totales = sum((pt.total for pt in serie_ventas), Decimal("0"))
        cantidad_ventas = sum((pt.cantidad for pt in serie_ventas), 0)

        # 4) (b) Top 5 productos por cantidad (en SQL, sin N+1 de ventas).
        ventas_subq = db.query(Venta.id).filter(Venta.fecha >= desde).subquery()
        top_rows = (
            db.query(
                VentaItem.producto_id,
                func.sum(VentaItem.cantidad).label("cantidad_total"),
                func.sum(
                    VentaItem.cantidad * VentaItem.precio_unitario - VentaItem.descuento
                ).label("importe_total"),
            )
            .filter(VentaItem.venta_id.in_(db.query(ventas_subq.c.id)))
            .group_by(VentaItem.producto_id)
            .order_by(func.sum(VentaItem.cantidad).desc())
            .limit(5)
            .all()
        )
        # Resolver nombres en UNA sola consulta (evita el N+1 del endpoint legacy).
        ids_top = [row[0] for row in top_rows]
        nombres = {}
        if ids_top:
            for pid, pnombre in (
                db.query(Producto.id, Producto.nombre)
                .filter(Producto.id.in_(ids_top))
                .all()
            ):
                nombres[pid] = pnombre
        top_productos = [
            ProductoVendido(
                producto_id=str(pid),
                nombre=nombres.get(pid, "Producto eliminado"),
                cantidad=Decimal(cantidad_total or 0),
                importe=Decimal(importe_total or 0),
            )
            for (pid, cantidad_total, importe_total) in top_rows
        ]

        # 5) (c) Distribución por método de pago (en SQL con GROUP BY).
        metodos_rows = (
            db.query(
                Venta.metodo_pago,
                func.sum(Venta.total).label("total"),
                func.count(Venta.id).label("cantidad"),
            )
            .filter(Venta.fecha >= desde)
            .group_by(Venta.metodo_pago)
            .all()
        )
        por_metodo_pago = [
            MetodoPagoDistribucion(
                metodo_pago=m,
                total=Decimal(t or 0),
                cantidad=int(c or 0),
            )
            for (m, t, c) in metodos_rows
        ]

        # 6) KPIs legacy de inventario (compatibilidad con el dashboard previo).
        productos = db.query(Producto).filter(Producto.activo.is_(True)).all()
        total_productos = len(productos)
        bajo_stock = sum(
            1 for p in productos if Decimal(p.stock) <= Decimal(p.stock_minimo)
        )
        ventas_hoy = (
            db.query(Venta)
            .filter(Venta.fecha >= _desde_dt(hoy))
            .filter(Venta.fecha <= _hasta_dt(hoy))
            .all()
        )
        total_ventas_hoy = sum((Decimal(v.total) for v in ventas_hoy), Decimal("0"))

        ultimo = (
            db.query(Arqueo)
            .filter(Arqueo.estado == "cerrado")
            .order_by(Arqueo.fecha_cierre.desc())
            .first()
        )
        ultimo_arqueo = (
            UltimoArqueoOut(
                id=str(ultimo.id),
                diferencia=(
                    Decimal(ultimo.diferencia)
                    if ultimo.diferencia is not None
                    else None
                ),
            )
            if ultimo is not None
            else None
        )

        return DashboardOut(
            agrupacion=agrupacion,
            rango=n,
            serie_ventas=serie_ventas,
            top_productos=top_productos,
            por_metodo_pago=por_metodo_pago,
            ventas_totales=ventas_totales,
            cantidad_ventas=cantidad_ventas,
            kpis=DashboardKpisOut(
                total_productos=total_productos,
                productos_bajo_stock=bajo_stock,
                ventas_hoy=total_ventas_hoy,
                ultimo_arqueo=ultimo_arqueo,
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al consultar dashboard: {str(exc)}",
        )
