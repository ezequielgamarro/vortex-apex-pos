-- ============================================================
-- SISTEMA DE PUNTO DE VENTA (QUIOSCO / DRUGSTORE)
-- Script SQL para ejecutar en el Editor SQL de Supabase
--
-- Tablas creadas (nombres y columnas consistentes con el backend):
--   • productos
--   • ventas
--   • venta_items        (detalle de ventas)
--   • arqueo             (caja)
--   • arqueo_movimientos (ingresos/egresos manuales)
-- Incluye triggers, funciones y políticas RLS.
-- ============================================================

-- ------------------------------------------------------------
-- Extensiones necesarias
-- ------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- TABLA: productos
-- ============================================================
CREATE TABLE IF NOT EXISTS public.productos (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre         TEXT NOT NULL,
    descripcion    TEXT,
    codigo_barras  TEXT UNIQUE,
    precio         NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (precio >= 0),
    costo          NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (costo >= 0),
    stock          INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    stock_minimo   INTEGER NOT NULL DEFAULT 0 CHECK (stock_minimo >= 0),
    categoria      TEXT,
    activo         BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en      TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en TIMESTAMPTZ
);

-- Índices para búsquedas frecuentes
CREATE INDEX IF NOT EXISTS idx_productos_nombre     ON public.productos (nombre);
CREATE INDEX IF NOT EXISTS idx_productos_categoria  ON public.productos (categoria);
CREATE INDEX IF NOT EXISTS idx_productos_activo     ON public.productos (activo);
CREATE INDEX IF NOT EXISTS idx_productos_bajo_stock ON public.productos (stock, stock_minimo) WHERE activo = TRUE;

-- ============================================================
-- TABLA: ventas
-- ============================================================
CREATE TABLE IF NOT EXISTS public.ventas (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    folio       TEXT UNIQUE,
    fecha       TIMESTAMPTZ NOT NULL DEFAULT now(),
    total       NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (total >= 0),
    metodo_pago TEXT NOT NULL DEFAULT 'efectivo'
                 CHECK (metodo_pago IN ('efectivo','tarjeta','transferencia','mixto')),
    cliente     TEXT NOT NULL DEFAULT 'Mostrador',
    creado_en   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ventas_fecha   ON public.ventas (fecha DESC);
CREATE INDEX IF NOT EXISTS idx_ventas_metodo  ON public.ventas (metodo_pago);
CREATE INDEX IF NOT EXISTS idx_ventas_cliente ON public.ventas (cliente);

-- ============================================================
-- TABLA: venta_items (detalle de ventas)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.venta_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    venta_id        UUID NOT NULL REFERENCES public.ventas(id) ON DELETE CASCADE,
    producto_id     UUID NOT NULL REFERENCES public.productos(id) ON DELETE RESTRICT,
    cantidad        INTEGER NOT NULL DEFAULT 1 CHECK (cantidad > 0),
    precio_unitario NUMERIC(12,2) NOT NULL CHECK (precio_unitario >= 0),
    descuento       NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (descuento >= 0)
);

CREATE INDEX IF NOT EXISTS idx_venta_items_venta    ON public.venta_items (venta_id);
CREATE INDEX IF NOT EXISTS idx_venta_items_producto ON public.venta_items (producto_id);

-- ============================================================
-- TABLA: arqueo (apertura/cierre de caja)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.arqueo (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fecha_apertura         TIMESTAMPTZ NOT NULL DEFAULT now(),
    fecha_cierre           TIMESTAMPTZ,
    monto_inicial          NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (monto_inicial >= 0),
    monto_esperado         NUMERIC(12,2),
    monto_real             NUMERIC(12,2),
    diferencia             NUMERIC(12,2),
    estado                 TEXT NOT NULL DEFAULT 'abierto' CHECK (estado IN ('abierto','cerrado')),
    observaciones_apertura TEXT,
    observaciones_cierre   TEXT,
    creado_en              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_arqueo_estado ON public.arqueo (estado);
CREATE INDEX IF NOT EXISTS idx_arqueo_fechas ON public.arqueo (fecha_apertura, fecha_cierre);

-- ============================================================
-- TABLA: arqueo_movimientos (ingresos/egresos manuales)
-- ============================================================
CREATE TABLE IF NOT EXISTS public.arqueo_movimientos (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    arqueo_id   UUID NOT NULL REFERENCES public.arqueo(id) ON DELETE CASCADE,
    tipo        TEXT NOT NULL CHECK (tipo IN ('ingreso','egreso')),
    monto       NUMERIC(12,2) NOT NULL CHECK (monto > 0),
    concepto    TEXT NOT NULL,
    metodo_pago TEXT NOT NULL DEFAULT 'efectivo',
    fecha       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_arqueo_mov_arqueo ON public.arqueo_movimientos (arqueo_id);
CREATE INDEX IF NOT EXISTS idx_arqueo_mov_tipo   ON public.arqueo_movimientos (tipo);

-- ============================================================
-- TRIGGER: registrar total de venta desde venta_items
-- ============================================================
CREATE OR REPLACE FUNCTION public.calcular_total_venta()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE public.ventas
       SET total = (
           SELECT COALESCE(SUM(cantidad * precio_unitario - descuento), 0)
             FROM public.venta_items
            WHERE venta_id = NEW.venta_id
       )
     WHERE id = NEW.venta_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_calcular_total_venta ON public.venta_items;
CREATE TRIGGER trg_calcular_total_venta
    AFTER INSERT OR UPDATE OR DELETE ON public.venta_items
    FOR EACH ROW EXECUTE FUNCTION public.calcular_total_venta();

-- ============================================================
-- TRIGGER: actualizar stock automáticamente
-- ============================================================
CREATE OR REPLACE FUNCTION public.actualizar_stock()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE public.productos
           SET stock = stock - NEW.cantidad,
               actualizado_en = now()
         WHERE id = NEW.producto_id;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE public.productos
           SET stock = stock + OLD.cantidad,
               actualizado_en = now()
         WHERE id = OLD.producto_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_actualizar_stock ON public.venta_items;
CREATE TRIGGER trg_actualizar_stock
    AFTER INSERT OR DELETE ON public.venta_items
    FOR EACH ROW EXECUTE FUNCTION public.actualizar_stock();

-- ============================================================
-- FUNCIÓN: productos con bajo stock
-- ============================================================
CREATE OR REPLACE FUNCTION public.productos_bajo_stock()
RETURNS SETOF public.productos AS $$
BEGIN
    RETURN QUERY
        SELECT p.*
          FROM public.productos p
         WHERE p.activo = TRUE
           AND p.stock <= p.stock_minimo
         ORDER BY (p.stock_minimo - p.stock) DESC;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- FUNCIÓN: cerrar caja y calcular total esperado
-- ============================================================
CREATE OR REPLACE FUNCTION public.cerrar_caja(
    p_arqueo_id UUID,
    p_monto_real NUMERIC
) RETURNS public.arqueo AS $$
DECLARE
    v_monto_inicial NUMERIC;
    v_total_ventas  NUMERIC;
    v_ingresos      NUMERIC;
    v_egresos       NUMERIC;
    v_esperado      NUMERIC;
    v_arqueo        public.arqueo;
BEGIN
    SELECT monto_inicial INTO v_monto_inicial
      FROM public.arqueo
     WHERE id = p_arqueo_id AND estado = 'abierto'
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Arqueo no existe o ya está cerrado';
    END IF;

    SELECT COALESCE(SUM(total), 0) INTO v_total_ventas
      FROM public.ventas
     WHERE fecha >= (SELECT fecha_apertura FROM public.arqueo WHERE id = p_arqueo_id);

    SELECT COALESCE(SUM(monto), 0) INTO v_ingresos
      FROM public.arqueo_movimientos
     WHERE arqueo_id = p_arqueo_id AND tipo = 'ingreso';

    SELECT COALESCE(SUM(monto), 0) INTO v_egresos
      FROM public.arqueo_movimientos
     WHERE arqueo_id = p_arqueo_id AND tipo = 'egreso';

    v_esperado = v_monto_inicial + v_total_ventas + v_ingresos - v_egresos;

    UPDATE public.arqueo
       SET estado         = 'cerrado',
           fecha_cierre   = now(),
           monto_esperado = v_esperado,
           monto_real     = p_monto_real,
           diferencia     = p_monto_real - v_esperado,
           observaciones_cierre = observaciones_cierre
     WHERE id = p_arqueo_id
     RETURNING * INTO v_arqueo;

    RETURN v_arqueo;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- VISTAS DE COMPATIBILIDAD (alias alternativos)
-- Permiten acceder con los nombres originales de la especificación
-- (detalle_ventas, arqueo_caja, precio_costo/precio_venta, monto_final)
-- sin romper el backend actual. Son vistas de lectura/consulta.
-- ============================================================

-- Vista "detalle_ventas" sobre la tabla venta_items
DROP VIEW IF EXISTS public.detalle_ventas;
CREATE VIEW public.detalle_ventas AS
SELECT
    id,
    venta_id,
    producto_id,
    cantidad,
    precio_unitario,
    descuento
FROM public.venta_items;

-- Vista "arqueo_caja" sobre la tabla arqueo
-- monto_final se expone como alias de monto_real (el total real contado al cerrar)
DROP VIEW IF EXISTS public.arqueo_caja;
CREATE VIEW public.arqueo_caja AS
SELECT
    id,
    fecha_apertura,
    fecha_cierre,
    monto_inicial,
    monto_real    AS monto_final,
    monto_esperado,
    monto_real,
    diferencia,
    estado,
    observaciones_apertura,
    observaciones_cierre,
    creado_en
FROM public.arqueo;

-- Vista "productos_precio": aliases precio_costo / precio_venta
-- (bajo este nombre para no colisionar con la tabla productos)
DROP VIEW IF EXISTS public.productos_precio;
CREATE VIEW public.productos_precio AS
SELECT
    id,
    nombre,
    descripcion,
    codigo_barras,
    costo        AS precio_costo,
    precio       AS precio_venta,
    stock,
    stock_minimo,
    categoria,
    activo,
    creado_en,
    actualizado_en
FROM public.productos;

-- ============================================================
-- POLÍTICAS DE SEGURIDAD (RLS)
-- ============================================================
ALTER TABLE public.productos          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ventas             ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.venta_items        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.arqueo             ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.arqueo_movimientos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "productos_policy" ON public.productos;
CREATE POLICY "productos_policy" ON public.productos FOR ALL USING (TRUE) WITH CHECK (TRUE);

DROP POLICY IF EXISTS "ventas_policy" ON public.ventas;
CREATE POLICY "ventas_policy" ON public.ventas FOR ALL USING (TRUE) WITH CHECK (TRUE);

DROP POLICY IF EXISTS "venta_items_policy" ON public.venta_items;
CREATE POLICY "venta_items_policy" ON public.venta_items FOR ALL USING (TRUE) WITH CHECK (TRUE);

DROP POLICY IF EXISTS "arqueo_policy" ON public.arqueo;
CREATE POLICY "arqueo_policy" ON public.arqueo FOR ALL USING (TRUE) WITH CHECK (TRUE);

DROP POLICY IF EXISTS "arqueo_movimientos_policy" ON public.arqueo_movimientos;
CREATE POLICY "arqueo_movimientos_policy" ON public.arqueo_movimientos FOR ALL USING (TRUE) WITH CHECK (TRUE);

-- ============================================================
-- TABLA: perfiles (usuarios + roles)
-- Se vincula al usuario autenticado de Supabase Auth (auth.users).
-- rol: 'admin' | 'cajero'
-- ============================================================
CREATE TABLE IF NOT EXISTS public.perfiles (
    id              UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    nombre_completo TEXT NOT NULL,
    rol             TEXT NOT NULL DEFAULT 'cajero' CHECK (rol IN ('admin','cajero')),
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_perfiles_rol ON public.perfiles (rol);

-- Desactivar RLS en perfiles para permitir lecturas amplias; la lógica
-- de rol se controla desde el backend con app/dependencies.py.
ALTER TABLE public.perfiles DISABLE ROW LEVEL SECURITY;

-- ============================================================
-- TRIGGER: crear perfil automáticamente al registrar un usuario
-- Crea un perfil 'cajero' por defecto en el alta de auth.users.
-- ============================================================
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.perfiles (id, nombre_completo, rol)
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data ->> 'nombre_completo', 'Usuario'),
        'cajero'
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ============================================================
-- FUNCIÓN: obtener el rol del usuario actual
-- Devuelve el rol desde JWT (útil en SQL y RLS avanzada).
-- ============================================================
CREATE OR REPLACE FUNCTION public.current_user_rol()
RETURNS TEXT AS $$
DECLARE
    v_rol TEXT;
BEGIN
    SELECT rol INTO v_rol
      FROM public.perfiles
     WHERE id = auth.uid();
    RETURN COALESCE(v_rol, 'cajero');
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;
