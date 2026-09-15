# -*- coding: utf-8 -*-
"""
seed_massive_data.py — Poblamiento masivo y DIRECTAMENTE en la BD local
(pos_local.db). Genera un volumen amplio de datos SINTÉTICOS para ejercitar
los módulos de inventario, ganancias, categorías, cuentas corrientes (fiado) y
el historial de cajas, SIN alterar usuarios administradores ni la estructura.

Transacciones agrupadas: se hace commit por entidad y luego un commit por cada
arqueo (ventas + ítems + movimientos + cierre cuadrados), lo que mantiene la
inserción en el orden de los milisegundos por bloque para SQLite.

NOTA DE COHERENCIA DE ESQUEMA (CERO ALUCINACIONES, auditado contra el repo):
La directiva mencionaba modelos `VentaDetalle`, `MovimientoCaja` y el método
de pago `debito`. El esquema REAL en `app/models/__init__.py` es:
    - detalle de venta      -> `VentaItem`          (no `VentaDetalle`)
    - movimiento de caja    -> `ArqueoMovimiento`   (no `MovimientoCaja`)
    - métodos de pago       -> {efectivo, tarjeta, transferencia, mixto,
                                cuenta_corriente}   (no existe `debito`)
Por lo tanto aquí se usan los contratos reales para que el cierre de caja
(`_calcular_totales`, en app/routers/arqueo.py) cuadre sin clasificaciones
desconocidas.

Ejecución (entorno virtual del proyecto):
    app/.venv/Scripts/python.exe seed_massive_data.py
"""

import os
import random
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Producto,
    Categoria,
    Cliente,
    Arqueo,
    ArqueoMovimiento,
    Venta,
    VentaItem,
    MovimientoCuenta,
)


# ------------------------------------------------------------------- helpers
def _utc_naive() -> datetime:
    """Ahora UTC *naive* (convención de marcas temporales del modelo)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _dinero(valor) -> Decimal:
    """Monto redondeado a 2 decimales (compatible con columnas Numeric)."""
    return Decimal(str(round(float(valor), 2)))


def _folio(ts: datetime, cont: int) -> str:
    """Folio único, patrón similar al de producción."""
    return f"V-{ts.strftime('%Y%m%d%H%M%S')}-{cont & 0xFFFFFF:06X}"


# --------------------------------------------------------------- constantes
CATEGORIAS = [
    "Cuidado Personal",
    "Barbería",
    "Bebidas",
    "Golosinas",
    "Almacén",
    "Cuidado Capilar",
    "Perfumería",
    "Accesorios",
]

BASE_NOMBRES = [
    "Shampoo",
    "Acondicionador",
    "Cremas Capilares",
    "Crema Facial",
    "Loción",
    "Jabón Líquido",
    "Perfume",
    "Agua",
    "Energética",
    "Gaseosa",
    "Chocolate",
    "Caramelo",
    "Galleta",
    "Arroz",
    "Fideos",
    "Aceite",
    "Cepillo",
    "Toalla",
    "Peine",
    "Navaja",
    "Gel Fijador",
    "Serum",
    "Vitamina C",
    "Barrita",
    "Snack",
    "Leche",
    "Café Molido",
    "Té",
    "Desodorante",
    "Cortante",
]

PRIMEROS = [
    "Luis",
    "María",
    "Carlos",
    "Ana",
    "Jorge",
    "Laura",
    "Pedro",
    "Sofía",
    "Miguel",
    "Fernanda",
    "Andrés",
    "Valentina",
    "Ricardo",
    "Carolina",
    "Diego",
    "Camila",
    "Pablo",
    "Daniela",
    "Santiago",
    "Lucía",
]
APELLIDOS = [
    "González",
    "Rodríguez",
    "Pérez",
    "Fernández",
    "López",
    "Martínez",
    "García",
    "Sánchez",
    "Romero",
    "Torres",
    "Silva",
    "Rojas",
    "Fuentes",
    "Castro",
    "Vargas",
    "Ramos",
    "Herrera",
    "Medina",
    "Aguirre",
    "Molina",
]

# Distribución ponderada de métodos de pago para la venta sintética.
METODOS = [
    "efectivo",
    "efectivo",
    "efectivo",
    "efectivo",
    "tarjeta",
    "transferencia",
    "mixto",
    "cuenta_corriente",
]
PESOS = [5, 5, 5, 5, 3, 3, 1, 2]


# ------------------------------------------------------------- generador de
# productoss / clientes -------------------------------------------------------
def generar_productos(nombres_cat, barcodes_existentes=None):
    """300 productos: costo $500..$15.000, margen 30%..80%, stock variado,
    código de barras numérico único de 12 dígitos. Precio = C + C*margen/100.
    `barcodes_existentes` evita colisionar con productos ya en la BD (idempotente)."""
    vistos = set(barcodes_existentes or [])
    pool = []
    for i in range(1, 301):
        cat = random.choice(nombres_cat)
        costo = random.randrange(500, 15001, 10)
        margen = random.randrange(30, 81)
        precio = int(round((costo + costo * margen / 100) / 10) * 10)
        precio = max(precio, costo)

        # Código de barras numérico único de 12 dígitos.
        bc = None
        while True:
            cand = str(random.randrange(10**11, 10**12))  # 12 dígitos
            if cand not in vistos:
                bc = cand
                vistos.add(cand)
                break

        # Distribución de stock: agotado / poco / normal.
        r = random.random()
        if r < 0.25:
            stock, stock_min = 0, random.randint(1, 5)
        elif r < 0.45:
            stock, stock_min = random.randint(1, 5), random.randint(1, 5)
        else:
            stock, stock_min = random.randint(25, 350), random.randint(6, 15)

        pool.append(
            Producto(
                nombre=f"{random.choice(BASE_NOMBRES)} {i}",
                descripcion=f"Producto sintético Nº {i} · {cat}",
                codigo_barras=bc,
                costo=_dinero(costo),
                porcentaje_ganancia=_dinero(margen),
                precio=_dinero(precio),
                stock=_dinero(stock),
                stock_minimo=_dinero(stock_min),
                categoria=cat,
                tipo_unidad=random.choice(("unidad", "peso", "porcion")),
                activo=True,
            )
        )
    return pool


def generar_clientes(n=40):
    clientes = []
    for _ in range(n):
        saldo = random.choice([0, 0, 0, random.randint(500, 25000)])
        clientes.append(
            Cliente(
                nombre=f"{random.choice(PRIMEROS)} {random.choice(APELLIDOS)}",
                telefono=f"9{random.randrange(1000000, 9999999)}",
                saldo_deuda=_dinero(saldo),
                activo=True,
            )
        )
    return clientes


def main():
    db = SessionLocal()
    resumen = {}
    try:
        # 0) Guardrail de consistencia: se necesita un catálogo previo.
        if db.query(Producto).count() == 0:
            raise RuntimeError(
                "No hay productos en pos_local.db. Levanta el backend una vez "
                "para que el lifespan cree/importe la BD y la seed base corra."
            )

        # 0b) IDEMPOTENCIA: si ya se aplicó la carga masiva (arqueos cerrados o
        #     ventas de prueba presentes), no duplicamos: sólo reportamos conteos.
        ya_sembrado = (
            db.query(Arqueo).filter(Arqueo.estado == "cerrado").count() > 0
        ) or db.query(Venta).count() > 0

        # 1) Categorías (8) — idempotentes (sin duplicar por nombre).
        exist = {c.nombre for c in db.query(Categoria).all()}
        nuevos = [Categoria(nombre=n) for n in CATEGORIAS if n not in exist]
        if nuevos:
            db.add_all(nuevos)
            db.commit()
        resumen["categorias_creadas_ahora"] = len(nuevos)
        resumen["categorias_total"] = db.query(Categoria).count()
        nombres_cat = [c.nombre for c in db.query(Categoria).all()]

        # ¿Ya hay 300+ productos del seed masivo? Distinguir por el conteo.
        hay_bulk_productos = db.query(Producto).count() >= 300

        if ya_sembrado and hay_bulk_productos:
            # No sembrar de nuevo; reportar volúmenes ya existentes.
            resumen["productos_nuevos"] = 0
            resumen["productos_total"] = db.query(Producto).count()
            resumen["clientes_nuevos"] = 0
            resumen["clientes_total"] = db.query(Cliente).count()
            resumen["arqueos_cerrados"] = (
                db.query(Arqueo).filter(Arqueo.estado == "cerrado").count()
            )
            resumen["ventas_totales"] = db.query(Venta).count()
            resumen["items_de_venta"] = db.query(VentaItem).count()
            resumen["movimientos_caja"] = db.query(ArqueoMovimiento).count()
            resumen["movimientos_cuenta"] = db.query(MovimientoCuenta).count()
            db.close()
            print("\n================ SEED MASIVO (IDEMPOTENTE) ==============")
            print(" Ya hay datos masivos: no se re-sembró nada.")
            print("---------------------------------------------------------")
            for k, v in resumen.items():
                print(f"  · {k:<26}: {v}")
            print("=========================================================")
            return resumen

        # 2) Productos (300). Los barcodes existentes (no nulos) se reservan
        #    para que el generador no colisione y la carga sea idempotente.
        bcs = [
            p.codigo_barras
            for p in db.query(Producto.codigo_barras).all()
            if p.codigo_barras
        ]
        db.add_all(
            generar_productos(
                nombres_cat if nombres_cat else CATEGORIAS, barcodes_existentes=bcs
            )
        )
        db.commit()
        resumen["productos_nuevos"] = 300
        resumen["productos_total"] = db.query(Producto).count()

        # 3) Clientes (40).
        clientes = generar_clientes(40)
        db.add_all(clientes)
        db.commit()
        resumen["clientes_nuevos"] = 40
        resumen["clientes_total"] = db.query(Cliente).count()

        # 4) Arqueos cerrados (30) en los últimos 60 días.
        hoy = _utc_naive().replace(second=0, microsecond=0)
        inicio = hoy - timedelta(days=60)
        ventanas = sorted(inicio + (hoy - inicio) * (idx / 31) for idx in range(1, 31))
        pool_prod = db.query(Producto).filter(Producto.activo.is_(True)).all()
        if not pool_prod:
            raise RuntimeError("Catálogo vacío tras sembrar productos.")

        cont_folio = random.randint(1, int(1e6))
        n_ventas = n_items = n_mov_caja = n_mov_cuenta = n_arqueos = 0
        n_abonos = 0

        for apertura in ventanas:
            duracion = timedelta(hours=random.uniform(3, 9))
            cierre = min(apertura + duracion, hoy)
            if cierre <= apertura:
                cierre = apertura + timedelta(hours=4)

            caja = Arqueo(
                fecha_apertura=apertura,
                fecha_cierre=cierre,
                estado="cerrado",
                monto_inicial=_dinero(random.randint(20000, 100000)),
                observaciones_apertura="Turno histórico (seed masivo)",
            )
            db.add(caja)
            db.flush()

            for _ in range(random.randint(18, 34)):
                ts = apertura + (cierre - apertura) * random.random()
                metodo = random.choices(METODOS, weights=PESOS, k=1)[0]

                cliente_cc, nombre_cliente = None, "Mostrador"
                if metodo == "cuenta_corriente":
                    cliente_cc = random.choice(clientes)
                    nombre_cliente = cliente_cc.nombre

                n_lin = random.randint(1, 5)
                elegidos = random.sample(
                    range(len(pool_prod)), min(n_lin, len(pool_prod))
                )
                total = Decimal("0")

                cont_folio += 1
                venta = Venta(
                    folio=_folio(ts, cont_folio),
                    fecha=ts,
                    total=Decimal("0"),
                    metodo_pago=metodo,
                    cliente=nombre_cliente,
                )
                db.add(venta)
                db.flush()  # fija venta.id dentro de esta misma transacción

                # Construir y enlazar ítems con la cabecera (venta_id real).
                items_venta = []
                for pos in elegidos:
                    prod = pool_prod[pos]
                    precio_u = Decimal(prod.precio)
                    cantidad = Decimal(random.randint(1, 4))
                    bruto = (cantidad * precio_u).quantize(Decimal("0.01"))
                    total += bruto

                    items_venta.append(
                        VentaItem(
                            venta_id=venta.id,
                            producto_id=prod.id,
                            cantidad=cantidad,
                            precio_unitario=precio_u,
                            descuento=Decimal("0"),
                        )
                    )
                    n_items += 1

                db.add_all(items_venta)
                venta.total = total.quantize(Decimal("0.01"))

                # Fiado: cargo + incremento de deuda (no entra a la gaveta).
                if metodo == "cuenta_corriente" and cliente_cc is not None:
                    cliente_cc.saldo_deuda = (
                        Decimal(cliente_cc.saldo_deuda or 0) + total
                    )
                    db.add(
                        MovimientoCuenta(
                            cliente_id=cliente_cc.id,
                            fecha=ts,
                            tipo="cargo",
                            monto=total.quantize(Decimal("0.01")),
                            venta_id=venta.id,
                            concepto=f"Venta a crédito {venta.folio}",
                        )
                    )
                    n_mov_cuenta += 1

                n_ventas += 1

            # Abonos (máx ~20) ligados a turnos pasados; ingreso a la gaveta.
            if n_abonos < 20:
                deudores = [c for c in clientes if c.saldo_deuda and c.saldo_deuda > 0]
                if deudores:
                    cli = random.choice(deudores)
                    monto = min(
                        random.randint(500, 8000), int(Decimal(cli.saldo_deuda or 0))
                    )
                    if monto > 0:
                        ts_ab = cierre - timedelta(minutes=random.randint(5, 90))
                        db.add(
                            ArqueoMovimiento(
                                arqueo_id=caja.id,
                                tipo="ingreso",
                                monto=_dinero(monto),
                                concepto=f"Abono {cli.nombre}",
                                metodo_pago="efectivo",
                                fecha=ts_ab,
                            )
                        )
                        db.add(
                            MovimientoCuenta(
                                cliente_id=cli.id,
                                fecha=ts_ab,
                                tipo="abono",
                                monto=_dinero(monto),
                                concepto="Abono a cuenta corriente",
                            )
                        )
                        cli.saldo_deuda = Decimal(cli.saldo_deuda or 0) - _dinero(monto)
                        n_mov_caja += 1
                        n_abonos += 1

            # ---- Cuadre del cierre por método (compat. _calcular_totales) ----
            ventas_efectivo = Decimal("0")
            for v in (
                db.query(Venta)
                .filter(
                    Venta.fecha >= apertura,
                    Venta.fecha <= cierre,
                    Venta.metodo_pago == "efectivo",
                )
                .all()
            ):
                ventas_efectivo += Decimal(v.total)

            ingresos = Decimal("0")
            for m in (
                db.query(ArqueoMovimiento)
                .filter(ArqueoMovimiento.arqueo_id == caja.id)
                .all()
            ):
                if m.tipo == "ingreso":
                    ingresos += Decimal(m.monto)

            esperado = Decimal(caja.monto_inicial or 0) + ventas_efectivo + ingresos
            real = esperado + Decimal(random.randint(-1500, 1500))
            if real < 0:
                real = esperado

            caja.monto_esperado = esperado.quantize(Decimal("0.01"))
            caja.monto_real = real.quantize(Decimal("0.01"))
            caja.diferencia = (real - esperado).quantize(Decimal("0.01"))
            caja.observaciones_cierre = "Cierre automático (seed masivo)"
            db.commit()  # transacción agrupada por arqueo
            n_arqueos += 1

        resumen.update(
            {
                "arqueos_cerrados": n_arqueos,
                "ventas_totales": n_ventas,
                "items_de_venta": n_items,
                "abonos": n_abonos,
                "movimientos_caja": n_mov_caja,
                "movimientos_cuenta_cargo": n_mov_cuenta,
            }
        )
    except Exception as exc:  # pragma: no cover
        db.rollback()
        print(f"\n[ERROR] El seed no pudo completarse: {exc}", file=sys.stderr)
        raise
    finally:
        db.close()

    # ---------------- Resumen por pantalla -----------------
    print("\n================ SEED MASIVO COMPLETADO ================")
    for k, v in resumen.items():
        print(f"  · {k:<26}: {v}")
    print("---------------------------------------------------------")
    print("  Usuarios administradores: NO modificados.")
    print("  Estructura / migraciones : intactas.")
    print("=========================================================")
    return resumen


if __name__ == "__main__":
    main()
