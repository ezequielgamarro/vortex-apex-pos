"""Modelos ORM de la aplicación.

Al importar este paquete, todos los modelos quedan registrados en
`Base.metadata`, de modo que `Base.metadata.create_all(bind=engine)` —ejecutado
en el arranque desde `app.main`— genere las tablas correspondientes.

CRÍTICO: usamos la misma `Base` de `app.database` (patrón `declarative_base()`).
Si definiéramos otra `Base` aquí, obtendríamos dos metadatas divergentes y
`create_all` no crearía estas tablas.

Convenciones para SQLite local:
- PKs de tipo UUID (compatibles con el contrato de las schemas Pydantic y el
  frontend) generados del lado Python, ya que SQLite no tiene `gen_random_uuid`.
- Fechas almacenadas como UTC *naive* para que las comparaciones por rangos
  (ventas de un arqueo, histórico diario) sean coherentes en SQLite.
- Montos como Numeric(12, 2) (SQLAlchemy devuelve Decimal al leer).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import relationship

from app.database import Base


def now_utc() -> datetime:
    """Devuelve la fecha/hora UTC actual como datetime naive.

    SQLite + SQLAlchemy DateTime comparan mejor sin offsets. Se elimina el
    offset para mantener marcas naive consistentes entre todas las columnas.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _uuid() -> uuid.UUID:
    """Genera un ID para defaults-Python (se evalúan por fila)."""
    return uuid.uuid4()


# ============================== PRODUCTOS ===================================


class Producto(Base):
    __tablename__ = "productos"

    # Tipo de unidad de venta / medición del producto.
    #   - 'unidad'  : se vende por pieza entera. stock en unidades.
    #   - 'peso'    : se vende por peso (kg) de forma continua; admite venta
    #                 por importe ($) y se descuenta la fracción de stock
    #                 exacta equivalente (stock en kg).
    #   - 'porcion' : se vende por porción/preparación.
    #   - 'metros'  : se vende por metro lineal (ferretería: cables, telas).
    #                 Se comporta como 'peso': admite importe ($) y fracciones.
    #   - 'litros'  : se vende por litro (ferretería: pinturas, solventes).
    #                 Se comporta como 'peso': admite importe ($) y fracciones.
    #   - 'servicio': no es un bien físico sino un servicio (librería:
    #                 copia/impresión). Por defecto NO descuenta stock si
    #                 stock == 0 (ilimitado); si stock > 0 actúa como tope.
    #
    # NOTA (escalabilidad): 'metros'/'litros' se tratan como VARIANTES CONTINUAS
    # (misma mecánica que 'peso': cantidad fraccionaria + venta por importe).
    # El frontend decide la etiqueta; el backend solo necesita saber si la
    # cantidad es fraccionaria o entera.
    TIPOS_UNIDAD = ("peso", "unidad", "porcion", "metros", "litros", "servicio")
    # Subconjunto de unidades que admiten cantidades fraccionarias / venta por
    # importe (misma mecánica de stock continuo que 'peso'). Centralizado para
    # no repetir la lista en router/schemas.
    TIPOS_UNIDAD_CONTINUOS = ("peso", "metros", "litros")
    # Subconjunto que representa un servicio (no bien físico).
    TIPOS_UNIDAD_SERVICIO = ("servicio",)

    id = Column(Uuid, primary_key=True, default=_uuid)
    nombre = Column(Text, nullable=False)
    descripcion = Column(Text, nullable=True)
    codigo_barras = Column(Text, unique=True, nullable=True)
    precio = Column(Numeric(12, 2), nullable=False, default=0)
    costo = Column(Numeric(12, 2), nullable=False, default=0)
    # Margen de ganancia objetivo (%). No se persiste derivado del precio para
    # permitir override manual del precio de venta; solo es una referencia/auto-cálculo.
    porcentaje_ganancia = Column(Numeric(6, 2), nullable=False, default=0)
    # `stock` y `stock_minimo` son Numeric para admitir unidades fraccionales
    # cuando `tipo_unidad == 'peso'` (p. ej. "2.75 kg"). 'unidad'/'porcion'
    # usan valores enteros; almacenarlos como Decimal no altera su lógica.
    stock = Column(Numeric(12, 3), nullable=False, default=0)
    stock_minimo = Column(Numeric(12, 3), nullable=False, default=0)
    categoria = Column(Text, nullable=True)
    tipo_unidad = Column(String(15), nullable=False, default="unidad")
    # --- Campos multi-rubro (indumentaria) ---
    marca = Column(String(80), nullable=True)
    talle = Column(String(40), nullable=True)
    color = Column(String(40), nullable=True)
    # `fecha_vencimiento`: control de perecibles (panaderia/alimentos).
    # Nullable: solo aplica a rubros con vencimiento.
    fecha_vencimiento = Column(DateTime, nullable=True)
    # --- Variantes de impresión (librería: productos tipo 'servicio') ---
    # Columnas dedicadas (no se reutiliza talle/color) para no mezclar semántica
    # y permitir evolución independiente. Nullable: el resto de rubros las ignora.
    tipo_papel = Column(String(40), nullable=True)  # ej. A4, Oficio, Foto
    color_bn = Column(String(20), nullable=True)  # ej. Color, B/N
    activo = Column(Boolean, nullable=False, default=True)
    creado_en = Column(DateTime, nullable=False, default=now_utc)
    actualizado_en = Column(DateTime, nullable=True)

    venta_items = relationship("VentaItem", back_populates="producto")

    def __repr__(self) -> str:
        return f"<Producto {self.nombre} ({self.tipo_unidad})>"


# =============================== VENTAS =====================================


class Venta(Base):
    __tablename__ = "ventas"

    id = Column(Uuid, primary_key=True, default=_uuid)
    folio = Column(String(40), unique=True, nullable=False)
    fecha = Column(DateTime, nullable=False, default=now_utc)
    total = Column(Numeric(12, 2), nullable=False, default=0)
    metodo_pago = Column(String(20), nullable=False, default="efectivo")
    cliente = Column(String(200), nullable=False, default="Mostrador")
    # Estado del ticket: 'activa' (default) | 'anulada'. Una venta anulada
    # se EXCLUYE de los totales de caja/reportes y su stock ya fue devuelto.
    estado = Column(String(20), nullable=False, default="activa")
    # Auditoria de la anulacion (trazabilidad: quien y cuando).
    anulada_en = Column(DateTime, nullable=True)
    anulada_por = Column(String(255), nullable=True)
    motivo_anulacion = Column(String(255), nullable=True)

    # Quién cobró la venta. NULL en ventas anteriores a esta versión. Define de
    # qué caja forma parte y qué cajero puede verla.
    usuario_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )

    # Vuelto en efectivo
    paga_con = Column(Numeric(12, 2), nullable=True)
    vuelto = Column(Numeric(12, 2), nullable=True)

    creado_en = Column(DateTime, nullable=False, default=now_utc)

    items = relationship(
        "VentaItem",
        back_populates="venta",
        cascade="all, delete-orphan",
        order_by="VentaItem.id",
    )

    def __repr__(self) -> str:
        return f"<Venta {self.folio} total={self.total}>"


class VentaItem(Base):
    __tablename__ = "venta_items"

    id = Column(Uuid, primary_key=True, default=_uuid)
    venta_id = Column(Uuid, ForeignKey("ventas.id", ondelete="CASCADE"), nullable=False)
    producto_id = Column(
        Uuid, ForeignKey("productos.id", ondelete="RESTRICT"), nullable=False
    )
    # `cantidad` es Numeric para registrar unidades fraccionales cuando el
    # producto es de tipo 'peso' (p. ej. 0.25 kg). Para 'unidad'/'porcion'
    # almacena valores enteros.
    cantidad = Column(Numeric(12, 3), nullable=False, default=1)
    precio_unitario = Column(Numeric(12, 2), nullable=False, default=0)
    descuento = Column(Numeric(12, 2), nullable=False, default=0)

    venta = relationship("Venta", back_populates="items")
    producto = relationship("Producto", back_populates="venta_items")

    def __repr__(self) -> str:
        return f"<VentaItem venta={self.venta_id} prod={self.producto_id}>"


# ================================ ARQUEO ====================================


class Arqueo(Base):
    __tablename__ = "arqueo"

    id = Column(Uuid, primary_key=True, default=_uuid)
    fecha_apertura = Column(DateTime, nullable=False, default=now_utc)
    fecha_cierre = Column(DateTime, nullable=True)
    monto_inicial = Column(Numeric(12, 2), nullable=False, default=0)
    monto_esperado = Column(Numeric(12, 2), nullable=True)
    monto_real = Column(Numeric(12, 2), nullable=True)
    diferencia = Column(Numeric(12, 2), nullable=True)
    estado = Column(String(20), nullable=False, default="abierto")
    observaciones_apertura = Column(Text, nullable=True)
    observaciones_cierre = Column(Text, nullable=True)
    creado_en = Column(DateTime, nullable=False, default=now_utc)

    # Dueño de la caja (quien la abrió). Cada usuario tiene su propia caja y solo
    # se le suman sus ventas. NULL = caja abierta antes de esta versión (se
    # trata como compartida hasta que se cierre).
    usuario_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )

    movimientos = relationship(
        "ArqueoMovimiento",
        back_populates="arqueo",
        cascade="all, delete-orphan",
        order_by="ArqueoMovimiento.fecha",
    )

    def __repr__(self) -> str:
        return f"<Arqueo {self.id} estado={self.estado}>"


class ArqueoMovimiento(Base):
    __tablename__ = "arqueo_movimientos"

    id = Column(Uuid, primary_key=True, default=_uuid)
    arqueo_id = Column(
        Uuid, ForeignKey("arqueo.id", ondelete="CASCADE"), nullable=False
    )
    tipo = Column(String(20), nullable=False)  # ingreso | egreso
    monto = Column(Numeric(12, 2), nullable=False)
    concepto = Column(Text, nullable=False)
    metodo_pago = Column(String(20), nullable=False, default="efectivo")
    fecha = Column(DateTime, nullable=False, default=now_utc)

    arqueo = relationship("Arqueo", back_populates="movimientos")

    def __repr__(self) -> str:
        return f"<ArqueoMovimiento {self.tipo} {self.monto}>"


# =============================== USUARIOS ===================================


class Usuario(Base):
    """Usuario local del punto de venta (login local, sin auth externa)."""

    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    nombre_completo = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    rol = Column(String(20), nullable=False, default="cajero")  # admin | cajero
    # Rubro del negocio (arquitectura multi-rubro). Determina que campos y
    # controles muestra la UI de inventario/POS para este usuario.
    # 'general' | 'panaderia_alimentos' | 'indumentaria' | 'ferreteria'
    # | 'libreria'. Los usuarios creados por un admin HEREDAN su rubro.
    rubro = Column(String(40), nullable=False, default="general")
    activo = Column(Boolean, default=True, nullable=False)
    creado_en = Column(DateTime, nullable=False, default=now_utc)

    def __repr__(self) -> str:
        return f"<Usuario {self.email} rol={self.rol}>"


# ============================== LICENCIA ==================================
# SaaS single-row: la instalacion local tiene exactamente una licencia.
# `cliente_id` identifica la instalacion ante el SuperAdmin (planilla CSV).


class Licencia(Base):
    """Licencia de uso de la instalacion (fila unica)."""

    __tablename__ = "licencia"

    id = Column(Integer, primary_key=True, default=1)  # singleton
    cliente_id = Column(String(120), unique=True, nullable=False, default="demo")
    # Fecha hasta la cual la licencia es valida (inclusive).
    fecha_vencimiento = Column(DateTime, nullable=True)
    # Dias de gracia tras el vencimiento antes de bloquear.
    dias_gracia = Column(Integer, nullable=False, default=3)
    # Ultima fecha conocida (fuente externa o local) al hacer ping.
    # Anti-trampas: si no hay internet, se avanza el tiempo desde aqui.
    ultimo_ping = Column(DateTime, nullable=True)
    estado = Column(String(20), nullable=False, default="activa")  # activa|suspendida
    actualizado_en = Column(DateTime, nullable=True)
    # Código firmado con el que se activó (VX1/VX2). Si está, el vencimiento y la
    # gracia se toman de LA FIRMA (se re-verifica), no de las columnas de arriba:
    # editar la base ya no sirve para extender la licencia.
    codigo_activacion = Column(Text, nullable=True)
    # Última serie de licencia (VX2) y de recuperación (VXR) aplicadas: impiden
    # repetir un código viejo.
    ultimo_serial = Column(BigInteger, nullable=True)
    ultimo_serial_rec = Column(BigInteger, nullable=True)

    def __repr__(self) -> str:
        return f"<Licencia {self.cliente_id} vence={self.fecha_vencimiento}>"


# ============================ CATEGORÍAS ==================================


class Categoria(Base):
    """Categoría de productos (tabla maestra).

    Se usa en paralelo con la columna `Producto.categoria` (texto). Se mantiene
    el texto en Producto para no romper vistas/endpoints existentes; esta tabla
    se ofrece como listado único y destino del modal de creación rápida.
    """

    __tablename__ = "categorias"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), unique=True, nullable=False)
    creado_en = Column(DateTime, nullable=False, default=now_utc)

    def __repr__(self) -> str:
        return f"<Categoria {self.nombre}>"


# ========================= CUENTAS CORRIENTES ==============================
# (Fiado a clientes)


class Cliente(Base):
    """Cliente del negocio con saldo de cuenta corriente (deuda fiada)."""

    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(200), nullable=False)
    telefono = Column(String(60), nullable=True)
    # Saldo actual de deuda del cliente (mayor = debe más).
    saldo_deuda = Column(Numeric(12, 2), nullable=False, default=0)
    activo = Column(Boolean, nullable=False, default=True)
    creado_en = Column(DateTime, nullable=False, default=now_utc)

    movimientos = relationship(
        "MovimientoCuenta",
        back_populates="cliente",
        order_by="MovimientoCuenta.fecha",
    )

    def __repr__(self) -> str:
        return f"<Cliente {self.nombre} saldo={self.saldo_deuda}>"


class MovimientoCuenta(Base):
    """Movimiento de cuenta corriente de un cliente (cargo/abono).

    - tipo == 'cargo': incrementa la deuda (venta fiada). Puede apuntar a una
      venta (venta_id).
    - tipo == 'abono': reduce la deuda (pago/adelanto). El dinero físico del
      abono ingresa a la Caja (ArqueoMovimiento de tipo ingreso) del turno.
    """

    __tablename__ = "movimientos_cuenta"

    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(
        Integer, ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False
    )
    fecha = Column(DateTime, nullable=False, default=now_utc)
    tipo = Column(String(20), nullable=False)  # 'cargo' | 'abono'
    monto = Column(Numeric(12, 2), nullable=False, default=0)
    venta_id = Column(Uuid, ForeignKey("ventas.id", ondelete="SET NULL"), nullable=True)
    concepto = Column(Text, nullable=True)

    cliente = relationship("Cliente", back_populates="movimientos")

    def __repr__(self) -> str:
        return f"<MovimientoCuenta cliente={self.cliente_id} {self.tipo} {self.monto}>"


# ========================= CONFIGURACIÓN DEL NEGOCIO =======================
# Patrón *Settings/Singleton Row* (Fowler, PoEAA): una única fila (id=1) que
# guarda la configuración del comercio. Se usa una tabla en lugar de
# localStorage porque el nombre del negocio es un dato del COMERCIO (no del
# navegador): debe sobrevivir a limpiezas de caché, re-instalaciones y ser
# compartido por todos los usuarios de la misma instalación.
# Escalable: futuros campos (dirección, RUT, teléfono, logo) se agregan como
# columnas nuevas sin refactorizar el acceso.


class ConfiguracionNegocio(Base):
    """Configuración global del negocio (fila única id=1)."""

    __tablename__ = "configuracion_negocio"

    # id fijo = 1 → garantiza el singleton a nivel de BD (no por convención).
    id = Column(Integer, primary_key=True, default=1)
    nombre = Column(String(200), nullable=False, default="")
    creado_en = Column(DateTime, nullable=False, default=now_utc)
    actualizado_en = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<ConfiguracionNegocio nombre={self.nombre!r}>"


__all__ = [
    "Base",
    "now_utc",
    "Producto",
    "Venta",
    "VentaItem",
    "Arqueo",
    "ArqueoMovimiento",
    "Usuario",
    "Categoria",
    "Cliente",
    "MovimientoCuenta",
    "ConfiguracionNegocio",
    "Licencia",
]
