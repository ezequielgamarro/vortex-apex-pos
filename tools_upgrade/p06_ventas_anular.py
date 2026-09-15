"""Módulo 3 — Anulación de ventas (reversión completa, atómica).

Diseño (por qué así):
  * La anulación NO borra la venta: cambia su `estado` a 'anulada' (soft-delete).
    Trazabilidad + auditoría son requisitos de un POS real; un DELETE destruye
    evidencia. La venta anulada se EXCLUYE de caja/reportes por filtro.
  * Reversión de stock por cada ítem (devuelve la cantidad física exacta).
  * Si la venta fue fiada (cuenta_corriente), se descuenta el CARGO del saldo
    del cliente y se registra un movimiento compensatorio ('abono') para que el
    estado de cuenta siga siendo auditable (no se muta el histórico).
  * La operación es ATÓMICA: un solo commit/rollback.
  * Regla de negocio: sólo se anulan ventas del arqueo (turno) ABIERTO. Anular
    una venta de un turno ya cerrado descuadraría un arqueo conciliado → se
    rechaza con 409 (integridad contable). Para esos casos, debe usarse un
    ajuste manual de caja.
"""
from tools_upgrade.patcher import apply

V = "app/routers/ventas.py"

# 1) Importar ArqueoMovimiento y el schema de anulacion.
apply(
    V,
    (
        "from app.models import (\n"
        "    Venta,\n"
        "    VentaItem,\n"
        "    Producto,\n"
        "    Arqueo,\n"
        "    Cliente,\n"
        "    MovimientoCuenta,\n"
        "    now_utc,\n"
        ")",
        "from app.models import (\n"
        "    Venta,\n"
        "    VentaItem,\n"
        "    Producto,\n"
        "    Arqueo,\n"
        "    ArqueoMovimiento,\n"
        "    Cliente,\n"
        "    MovimientoCuenta,\n"
        "    now_utc,\n"
        ")",
    ),
)

apply(
    V,
    (
        "from app.schemas.venta import (\n"
        "    VentaCreate,\n"
        "    VentaOut,\n"
        "    VentaDetalleOut,\n"
        "    VentaItemOut,\n"
        "    VentaItemHistorialOut,\n"
        "    VentaHistorialOut,\n"
        ")",
        "from app.schemas.venta import (\n"
        "    VentaCreate,\n"
        "    VentaOut,\n"
        "    VentaDetalleOut,\n"
        "    VentaItemOut,\n"
        "    VentaItemHistorialOut,\n"
        "    VentaHistorialOut,\n"
        "    AnulacionOut,\n"
        ")",
    ),
)

# 2) Endpoint de anulacion, insertado antes de `def _serializar_historial`.
ANCHOR_HIST = 'def _serializar_historial(venta: Venta) -> VentaHistorialOut:'
ANULAR_EP = '''@router.post(
    "/{venta_id}/anular",
    response_model=AnulacionOut,
    summary="Anular una venta y revertir stock/saldo/caja (solo admin)",
)
def anular_venta(
    venta_id: UUID,
    usuario: UsuarioActual = Depends(requiere_rol("admin")),
    db: Session = Depends(get_db),
):
    """Anula una venta ACTIVA del turno abierto, revirtiendo todos sus efectos.

    Efectos revertidos (en una única transacción atómica):
      1. Stock: se devuelve la cantidad física exacta de cada ítem.
      2. Cuenta corriente: si fue fiado, se descuenta el cargo del saldo y se
         registra un movimiento compensatorio 'abono' (auditoría).
      3. Caja: la venta sale de los totales por filtro de estado ('anulada'),
         de modo que la gaveta esperada queda consistente sin movimientos extra.

    Reglas:
      - Solo admin (requiere_rol).
      - No se permite anular una venta ya anulada (409).
      - No se permite anular una venta de un turno CERRADO (409): descuadraría
        un arqueo conciliado. Usar ajuste manual de caja en ese caso.
    """
    try:
        venta = db.query(Venta).filter(Venta.id == venta_id).first()
        if venta is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Venta no encontrada",
            )
        if (venta.estado or "activa") == "anulada":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Esta venta ya fue anulada.",
            )

        # La venta debe pertenecer al turno ABIERTO para poder anularse.
        caja_abierta = db.query(Arqueo).filter(Arqueo.estado == "abierto").first()
        if caja_abierta is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "No hay una caja abierta. Solo pueden anularse ventas del "
                    "turno en curso."
                ),
            )
        if venta.fecha < caja_abierta.fecha_apertura:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Esta venta pertenece a un turno anterior ya cerrado. Para "
                    "corregirla, registra un ajuste manual en la caja actual."
                ),
            )

        # 1) Revertir stock ítem por ítem.
        stock_total = 0
        for it in venta.items:
            producto = db.query(Producto).filter(Producto.id == it.producto_id).first()
            if producto is None:
                continue
            producto.stock = Decimal(producto.stock or 0) + Decimal(it.cantidad)
            producto.actualizado_en = now_utc()
            stock_total += 1

        # 2) Revertir saldo de cuenta corriente (si fue fiado).
        saldo_cc_ajustado = None
        if venta.metodo_pago == "cuenta_corriente":
            mov = (
                db.query(MovimientoCuenta)
                .filter(
                    MovimientoCuenta.venta_id == venta.id,
                    MovimientoCuenta.tipo == "cargo",
                )
                .first()
            )
            if mov is not None:
                cliente = (
                    db.query(Cliente).filter(Cliente.id == mov.cliente_id).first()
                )
                if cliente is not None:
                    cliente.saldo_deuda = Decimal(cliente.saldo_deuda or 0) - Decimal(
                        mov.monto
                    )
                    if cliente.saldo_deuda < 0:
                        cliente.saldo_deuda = Decimal("0")
                    saldo_cc_ajustado = cliente.saldo_deuda
                    # Movimiento compensatorio (auditoría; no se borra el cargo).
                    db.add(
                        MovimientoCuenta(
                            cliente_id=cliente.id,
                            tipo="abono",
                            monto=Decimal(mov.monto),
                            venta_id=venta.id,
                            concepto=f"Anulación de venta {venta.folio}",
                        )
                    )

        # 3) Marcar la venta como anulada (soft-delete + auditoría).
        venta.estado = "anulada"
        venta.anulada_en = now_utc()
        venta.anulada_por = usuario.email or usuario.nombre

        db.commit()
        db.refresh(venta)

        return AnulacionOut(
            venta_id=venta.id,
            folio=venta.folio,
            estado=venta.estado,
            total_revertido=Decimal(venta.total),
            stock_devuelto=stock_total,
            saldo_cc_ajustado=saldo_cc_ajustado,
            mensaje=(
                f"Venta {venta.folio} anulada. Stock y cuenta corriente revertidos."
            ),
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:  # pragma: no cover
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al anular la venta: {str(exc)}",
        )


'''
apply(V, (ANCHOR_HIST, ANULAR_EP + ANCHOR_HIST))

print("[ventas anulacion] OK")
