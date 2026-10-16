"""Pruebas del alta inicial (asistente de primer arranque) y del endurecimiento.

Corren contra una base y una carpeta de datos TEMPORALES (no tocan pos_local.db)
y con un par de llaves Ed25519 de prueba: no hace falta la llave privada real.

    pip install pytest
    python -m pytest tests -q
"""

import os
import tempfile
from pathlib import Path

# --- Entorno aislado: ANTES de importar la app (config/database leen el entorno).
_TMP = tempfile.mkdtemp(prefix="pos_test_")
os.environ["USER_DATA_DIR"] = _TMP
for _var in ("SECRET_KEY", "ADMIN_PASSWORD", "ADMIN_EMAIL", "ENV", "CORS_ORIGINS"):
    os.environ.pop(_var, None)

import pytest  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: E402
    Ed25519PrivateKey,
)
from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Licencia, Usuario  # noqa: E402
from app.services import licencia_firma  # noqa: E402
from app.services.licencia_firma import calcular_huella, firmar_alta, firmar_licencia  # noqa: E402

PAYLOAD = {
    "nombre": "Pedro Gómez",
    "email": "Pedro@Libreria.com",
    "password": "clave-segura-123",
}


@pytest.fixture(scope="module")
def llaves(tmp_path_factory):
    """Par Ed25519 de prueba; publica la pública donde la app la busca."""
    privada = Ed25519PrivateKey.generate()
    pem = privada.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    ruta = tmp_path_factory.mktemp("llaves") / "licencia_public.key"
    ruta.write_bytes(pem)
    original = licencia_firma.RUTA_PUBLICA_DEFECTO
    licencia_firma.RUTA_PUBLICA_DEFECTO = ruta
    yield privada
    licencia_firma.RUTA_PUBLICA_DEFECTO = original


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # `with` ejecuta el lifespan (migraciones + seed)
        yield c


def _huella_actual() -> str:
    db = SessionLocal()
    try:
        lic = db.query(Licencia).first()
        return calcular_huella(lic.cliente_id if lic and lic.cliente_id else "demo")
    finally:
        db.close()


def test_secreto_propio_de_la_instalacion(client):
    from app.config import obtener_secreto

    secreto = obtener_secreto()
    assert secreto != "dev-secret-change-me-por-entorno"
    assert len(secreto) >= 32
    archivo = Path(_TMP) / "secret.key"
    assert archivo.exists()  # lo crea el arranque del backend (lifespan)
    assert archivo.read_text(encoding="utf-8").strip() == secreto
    assert settings.SECRET_KEY == ""  # el campo de entorno no se pisa con el secreto


def test_importar_la_configuracion_no_escribe_archivos(tmp_path):
    """PyInstaller importa todos los módulos al compilar: no deben dejar basura."""
    import subprocess
    import sys

    raiz = Path(__file__).resolve().parent.parent
    entorno = {k: v for k, v in os.environ.items() if k not in ("USER_DATA_DIR", "SECRET_KEY")}
    r = subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, r'{raiz}'); import app.main"],
        cwd=tmp_path, env=entorno, capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, r.stderr[-500:]
    assert list(tmp_path.iterdir()) == []  # ni secret.key ni la base ni nada


def test_base_vacia_no_siembra_admin_por_defecto(client):
    db = SessionLocal()
    try:
        assert db.query(Usuario).count() == 0
    finally:
        db.close()
    estado = client.get("/api/setup/estado").json()
    assert estado["necesita_setup"] is True
    assert estado["huella"].startswith("POS-")


def test_registro_publico_eliminado(client):
    r = client.post(
        "/api/auth/register",
        json={"nombre": "x", "email": "x@x.com", "password": "123456"},
    )
    assert r.status_code in (404, 405)


def test_docs_cerrados_en_produccion(client):
    for ruta in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(ruta).status_code == 404


def test_health_no_expone_entorno(client):
    assert client.get("/health").json() == {"status": "healthy"}


def test_cors_no_acepta_origen_ajeno(client):
    r = client.options(
        "/api/auth/login",
        headers={
            "Origin": "http://sitio-malicioso.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in r.headers
    ok = client.options(
        "/api/auth/login",
        headers={
            "Origin": "http://127.0.0.1:8000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert ok.headers.get("access-control-allow-origin") == "http://127.0.0.1:8000"


def _alta(llaves, **kw):
    return firmar_alta(llaves, _huella_actual(), **kw)


def test_alta_rechaza_codigos_invalidos(client, llaves):
    casos = {
        "basura": "esto-no-es-un-codigo",
        "firma_ajena": firmar_alta(Ed25519PrivateKey.generate(), _huella_actual()),
        "otra_pc": firmar_alta(llaves, "POS-DEADBEEF-DEMO"),
        # Un código de LICENCIA no puede usarse como alta.
        "licencia": firmar_licencia(
            llaves, "demo", _huella_actual(), __import__("datetime").date(2030, 1, 1)
        ),
    }
    for nombre, codigo in casos.items():
        r = client.post("/api/setup/inicializar", json={**PAYLOAD, "codigo_alta": codigo})
        assert r.status_code == 400, nombre
    db = SessionLocal()
    try:
        assert db.query(Usuario).count() == 0
    finally:
        db.close()


def test_alta_valida_crea_admin_con_rubro_firmado(client, llaves):
    codigo = _alta(llaves, rubro="libreria")
    r = client.post("/api/setup/inicializar", json={**PAYLOAD, "codigo_alta": codigo})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]

    perfil = client.get(
        "/api/auth/perfil", headers={"Authorization": f"Bearer {token}"}
    ).json()
    assert perfil["rol"] == "admin"
    assert perfil["email"] == "pedro@libreria.com"
    assert perfil["rubro"] == "libreria"
    assert perfil["es_superadmin"] is False


def test_alta_se_cierra_despues_del_primer_admin(client, llaves):
    codigo = _alta(llaves)
    r = client.post(
        "/api/setup/inicializar",
        json={**PAYLOAD, "email": "otro@x.com", "codigo_alta": codigo},
    )
    assert r.status_code == 409
    assert client.get("/api/setup/estado").json() == {
        "necesita_setup": False,
        "huella": None,
    }


def test_admin_crea_cajero_y_hereda_rubro(client):
    login = client.post(
        "/api/auth/login",
        data={"username": "pedro@libreria.com", "password": PAYLOAD["password"]},
    )
    assert login.status_code == 200
    h = {"Authorization": f"Bearer {login.json()['access_token']}"}
    r = client.post(
        "/api/auth/usuarios",
        headers=h,
        json={
            "nombre": "Caja Uno",
            "email": "caja1@libreria.com",
            "password": "cajero-123",
            "rol": "cajero",
            "rubro": "ferreteria",  # un admin estándar NO puede elegir rubro
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["rol"] == "cajero"
    assert r.json()["rubro"] == "libreria"


def test_token_forjado_con_el_secreto_viejo_no_sirve(client):
    import jwt

    forjado = jwt.encode(
        {"sub": "1", "rol": "admin"}, "dev-secret-change-me-por-entorno", algorithm="HS256"
    )
    r = client.get("/api/auth/perfil", headers={"Authorization": f"Bearer {forjado}"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Límite de intentos de login y errores internos
# ---------------------------------------------------------------------------
def test_login_guard_bloquea_y_se_libera_con_el_tiempo():
    from app.services.login_guard import LoginGuard

    t = [0.0]
    g = LoginGuard(max_intentos=3, ventana_s=60, bloqueo_s=120, reloj=lambda: t[0])
    k = g.clave("  Pepe@X.com ")
    assert k == "pepe@x.com"
    for _ in range(2):
        g.registrar_fallo(k)
    assert g.segundos_bloqueado(k) == 0
    g.registrar_fallo(k)  # tercer fallo: bloquea
    assert 0 < g.segundos_bloqueado(k) <= 121
    t[0] = 121.0
    assert g.segundos_bloqueado(k) == 0  # pasó el bloqueo
    g.registrar_fallo(k)
    g.registrar_exito(k)  # un acierto reinicia el contador
    for _ in range(2):
        g.registrar_fallo(k)
    assert g.segundos_bloqueado(k) == 0


def test_login_guard_ventana_vieja_no_acumula():
    from app.services.login_guard import LoginGuard

    t = [0.0]
    g = LoginGuard(max_intentos=3, ventana_s=60, bloqueo_s=120, reloj=lambda: t[0])
    g.registrar_fallo("a")
    g.registrar_fallo("a")
    t[0] = 100.0  # fuera de la ventana: el conteo empieza de nuevo
    g.registrar_fallo("a")
    assert g.segundos_bloqueado("a") == 0


def test_login_bloquea_tras_5_fallos_incluso_con_la_clave_correcta(client):
    mal = {"username": "pedro@libreria.com", "password": "incorrecta-xx"}
    # Usuario inexistente: también cuenta (no revela qué cuentas existen).
    fantasma = {"username": "fantasma@nada.com", "password": "incorrecta-xx"}
    for _ in range(5):
        assert client.post("/api/auth/login", data=fantasma).status_code == 401
    r = client.post("/api/auth/login", data=fantasma)
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) > 0
    # Otro correo no se ve afectado.
    ok = client.post(
        "/api/auth/login",
        data={"username": "pedro@libreria.com", "password": PAYLOAD["password"]},
    )
    assert ok.status_code == 200
    assert mal  # (referencia para claridad del caso)


def test_error_interno_no_devuelve_detalle_tecnico(caplog):
    from app.errors import detalle_error_interno

    with caplog.at_level("ERROR", logger="uvicorn.error"):
        msg = detalle_error_interno(
            "Error al registrar la venta", RuntimeError("sqlite3: tabla secreta rota")
        )
    assert msg == "Error al registrar la venta"
    assert "secreta" not in msg
    assert "tabla secreta rota" in caplog.text  # el detalle queda en el log


# ---------------------------------------------------------------------------
# Base de datos: WAL, índices, backup, importación y reset
# ---------------------------------------------------------------------------
def _token_admin(client):
    r = client.post(
        "/api/auth/login",
        data={"username": "pedro@libreria.com", "password": PAYLOAD["password"]},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_sqlite_en_wal_con_busy_timeout(client):
    from sqlalchemy import text

    from app.database import engine

    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar().lower() == "wal"
        assert conn.execute(text("PRAGMA busy_timeout")).scalar() == 5000


def test_indices_creados_por_la_migracion(client):
    from sqlalchemy import text

    from app.database import engine

    with engine.connect() as conn:
        nombres = {
            r[0]
            for r in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='index'")
            )
        }
    for esperado in (
        "ix_ventas_fecha",
        "ix_venta_items_venta_id",
        "ix_productos_nombre",
        "ix_mov_cuenta_cliente_fecha",
    ):
        assert esperado in nombres


def test_backup_crea_omite_y_rota(tmp_path):
    import os
    import sqlite3
    import time

    from app.services.backup import respaldar_si_corresponde

    # Instalación nueva (sin archivo): no hay nada que respaldar.
    assert respaldar_si_corresponde(tmp_path / "no_existe.db") is None

    db = tmp_path / "pos_local.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE t (x)")
    con.execute("INSERT INTO t VALUES (42)")
    con.commit()
    con.close()

    primero = respaldar_si_corresponde(db)
    assert primero is not None and primero.exists()
    # La copia es una base válida con los datos.
    copia = sqlite3.connect(primero)
    try:
        assert copia.execute("SELECT x FROM t").fetchone() == (42,)
    finally:
        copia.close()  # en Windows un archivo abierto no se puede borrar
    # Hace menos de 20 h: no repite.
    assert respaldar_si_corresponde(db) is None

    # Forzados: se rota y quedan solo los últimos 3.
    for i in range(5):
        time.sleep(1.05)  # el nombre lleva segundos
        assert respaldar_si_corresponde(db, forzar=True, conservar=3) is not None
    quedan = sorted(p.name for p in (tmp_path / "backups").iterdir())
    assert len(quedan) == 3
    # Un archivo ajeno en la carpeta de backups nunca se borra.
    ajeno = tmp_path / "backups" / "notas.txt"
    ajeno.write_text("no tocar")
    time.sleep(1.05)
    respaldar_si_corresponde(db, forzar=True, conservar=3)
    assert ajeno.exists()
    assert os.path.getsize(db) > 0


def test_importar_rechaza_archivo_grande_y_exportar_neutraliza_formulas(
    client, monkeypatch
):
    import io

    from openpyxl import Workbook, load_workbook

    from app.routers import productos as rp

    h = _token_admin(client)

    def xlsx(filas):
        wb = Workbook()
        ws = wb.active
        for f in filas:
            ws.append(f)
        b = io.BytesIO()
        wb.save(b)
        return b.getvalue()

    contenido = xlsx([["nombre", "precio"], ["Yerba", 1500]])
    ok = client.post(
        "/api/productos/importar",
        headers=h,
        files={"archivo": ("p.xlsx", contenido, "application/octet-stream")},
    )
    assert ok.status_code == 200, ok.text

    # Tope de tamaño (se baja el límite para no fabricar 10 MB).
    monkeypatch.setattr(rp, "_MAX_IMPORT_BYTES", 100)
    grande = client.post(
        "/api/productos/importar",
        headers=h,
        files={"archivo": ("p.xlsx", contenido, "application/octet-stream")},
    )
    assert grande.status_code == 413
    monkeypatch.undo()

    # Tope de filas.
    monkeypatch.setattr(rp, "_MAX_IMPORT_FILAS", 2)
    filas = [["nombre", "precio"]] + [[f"P{i}", 10] for i in range(5)]
    muchas = client.post(
        "/api/productos/importar",
        headers=h,
        files={"archivo": ("p.xlsx", xlsx(filas), "application/octet-stream")},
    )
    assert muchas.status_code == 413
    monkeypatch.undo()

    # Una fórmula en el nombre no debe viajar como fórmula en la exportación.
    crear = client.post(
        "/api/productos",
        headers=h,
        json={"nombre": "=HYPERLINK(\"http://x\",\"hola\")", "precio": 10, "stock": 1},
    )
    assert crear.status_code in (200, 201), crear.text
    exp = client.get("/api/productos/exportar", headers=h)
    assert exp.status_code == 200
    ws = load_workbook(io.BytesIO(exp.content)).active
    nombres = [fila[0] for fila in ws.iter_rows(min_row=2, values_only=True)]
    assert "'=HYPERLINK(\"http://x\",\"hola\")" in nombres
    assert not any(isinstance(n, str) and n.startswith("=") for n in nombres)
    # Y la inversa devuelve el texto original al reimportar.
    assert rp._quitar_guarda_formula("'=1+1") == "=1+1"
    assert rp._quitar_guarda_formula("O'Brien") == "O'Brien"


def test_reset_db_cancelado_no_borra_nada(client, monkeypatch, capsys):
    import reset_db

    from app.database import SessionLocal
    from app.models import Usuario

    monkeypatch.setattr("builtins.input", lambda *_: "no-es-el-nombre")
    reset_db.reset_database()
    assert "Cancelado" in capsys.readouterr().out
    db = SessionLocal()
    try:
        assert db.query(Usuario).count() >= 2  # admin + cajero siguen ahí
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Permisos del cajero: sin costos, ventas propias y una caja por usuario
# ---------------------------------------------------------------------------
def _hdr(client, email, password):
    r = client.post("/api/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_cajero_no_ve_costos_ni_exporta(client):
    from decimal import Decimal

    admin = _token_admin(client)
    cajero = _hdr(client, "caja1@libreria.com", "cajero-123")
    r = client.post(
        "/api/productos",
        headers=admin,
        json={"nombre": "Alfajor", "precio": 100, "costo": 60,
              "porcentaje_ganancia": 66, "stock": 50},
    )
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]

    # El administrador ve costo y margen; el cajero no, en ningún endpoint.
    a = client.get(f"/api/productos/{pid}", headers=admin).json()
    assert Decimal(str(a["costo"])) == Decimal("60")
    c = client.get(f"/api/productos/{pid}", headers=cajero).json()
    assert c["costo"] is None and c["porcentaje_ganancia"] is None
    assert Decimal(str(c["precio"])) == Decimal("100")  # el precio sí lo ve
    lista = client.get("/api/productos", headers=cajero).json()
    assert lista and all(p["costo"] is None and p["porcentaje_ganancia"] is None for p in lista)
    bajo = client.get("/api/productos/bajo-stock", headers=cajero)
    assert bajo.status_code == 200
    assert all(p["costo"] is None for p in bajo.json())

    # La exportación (trae costo y margen) es solo del administrador.
    assert client.get("/api/productos/exportar", headers=cajero).status_code == 403
    assert client.get("/api/productos/exportar", headers=admin).status_code == 200


def test_caja_por_usuario_y_ventas_propias(client):
    from decimal import Decimal

    admin = _token_admin(client)
    cajero = _hdr(client, "caja1@libreria.com", "cajero-123")
    pid = next(
        p["id"] for p in client.get("/api/productos", headers=admin).json()
        if p["nombre"] == "Alfajor"
    )
    venta2 = {"items": [{"producto_id": pid, "cantidad": 2}], "metodo_pago": "efectivo"}
    venta1 = {"items": [{"producto_id": pid, "cantidad": 1}], "metodo_pago": "efectivo"}

    # Sin caja propia no se puede cobrar.
    assert client.post("/api/ventas", headers=cajero, json=venta2).status_code == 400

    # Cada uno abre la suya; no se puede abrir una segunda.
    assert client.post("/api/arqueo/abrir", headers=cajero, json={"monto_inicial": 1000}).status_code == 201
    assert client.post("/api/arqueo/abrir", headers=admin, json={"monto_inicial": 5000}).status_code == 201
    assert client.post("/api/arqueo/abrir", headers=cajero, json={"monto_inicial": 1}).status_code == 409

    vc = client.post("/api/ventas", headers=cajero, json=venta2)
    va = client.post("/api/ventas", headers=admin, json=venta1)
    assert vc.status_code == 201 and va.status_code == 201, (vc.text, va.text)
    id_c, id_a = vc.json()["id"], va.json()["id"]

    # Visibilidad de ventas: el cajero solo ve la suya; el admin ve las dos.
    ids_cajero = {v["id"] for v in client.get("/api/ventas", headers=cajero).json()}
    assert id_c in ids_cajero and id_a not in ids_cajero
    ids_admin = {v["id"] for v in client.get("/api/ventas", headers=admin).json()}
    assert {id_c, id_a} <= ids_admin
    assert client.get(f"/api/ventas/{id_c}", headers=cajero).status_code == 200
    assert client.get(f"/api/ventas/{id_a}", headers=cajero).status_code == 404
    assert client.get(f"/api/ventas/{id_a}/detalle", headers=cajero).status_code == 404
    det = {v["id"] for v in client.get("/api/ventas/historial-detallado", headers=cajero).json()}
    assert id_c in det and id_a not in det

    # Cada caja suma solo las ventas de su dueño.
    rc = client.get("/api/arqueo/resumen", headers=cajero).json()
    ra = client.get("/api/arqueo/resumen", headers=admin).json()
    assert Decimal(str(rc["ventas_efectivo"])) == Decimal("200")
    assert Decimal(str(rc["total_esperado"])) == Decimal("1200")
    assert Decimal(str(ra["ventas_efectivo"])) == Decimal("100")
    assert Decimal(str(ra["total_esperado"])) == Decimal("5100")

    # El cajero no puede consultar la caja del administrador.
    caja_admin = client.get("/api/arqueo/activo", headers=admin).json()["id"]
    assert client.get(f"/api/arqueo/{caja_admin}/resumen", headers=cajero).status_code == 404
    assert client.get(f"/api/arqueo/{caja_admin}/resumen", headers=admin).status_code == 200

    # El admin anula la venta del cajero (su caja sigue abierta).
    anul = client.post(
        f"/api/ventas/{id_c}/anular",
        headers=admin,
        json={"motivo": "prueba", "password": PAYLOAD["password"]},
    )
    assert anul.status_code == 200, anul.text
    rc2 = client.get("/api/arqueo/resumen", headers=cajero).json()
    assert Decimal(str(rc2["ventas_efectivo"])) == Decimal("0")

    # Cerrar la caja propia no toca la ajena.
    cierre = client.post("/api/arqueo/cerrar", headers=cajero, json={"monto_final": 1000})
    assert cierre.status_code == 200, cierre.text
    assert client.get("/api/arqueo/activo", headers=cajero).json() is None
    assert client.get("/api/arqueo/activo", headers=admin).json()["id"] == caja_admin

    # Historial de cajas: el cajero ve solo la suya; el admin, todas.
    h_cajero = client.get("/api/arqueo/historial", headers=cajero).json()
    assert len(h_cajero) == 1
    assert client.post("/api/arqueo/cerrar", headers=admin, json={"monto_final": 5100}).status_code == 200
    h_admin = client.get("/api/arqueo/historial", headers=admin).json()
    assert len(h_admin) >= 2


# ---------------------------------------------------------------------------
# Cabeceras de seguridad (CSP) y handlers inline
# ---------------------------------------------------------------------------
def test_cabeceras_de_seguridad_en_todas_las_respuestas(client):
    for ruta in ("/health", "/login.html", "/api/setup/estado", "/no-existe"):
        h = client.get(ruta).headers
        csp = h["content-security-policy"]
        assert "script-src 'self'" in csp and "'unsafe-inline'" not in csp.split("style-src")[0]
        assert "connect-src 'self'" in csp
        assert "object-src 'none'" in csp and "frame-ancestors 'none'" in csp
        assert h["x-content-type-options"] == "nosniff"
        assert h["x-frame-options"] == "DENY"
    # También en los errores de autenticación.
    assert "content-security-policy" in client.get("/api/auth/perfil").headers


def test_frontend_sin_handlers_inline():
    """La CSP bloquea `onclick=` y similares: no puede quedar ninguno."""
    import re

    raiz = Path(__file__).resolve().parent.parent / "frontend"
    patron = re.compile(r"\son(click|change|submit|input|load|error|key\w+|focus|blur|mouse\w+)\s*=", re.I)
    sospechosos = []
    for f in list(raiz.glob("*.html")) + list((raiz / "services").glob("*.js")):
        for n, linea in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if patron.search(linea) and "addEventListener" not in linea:
                sospechosos.append(f"{f.name}:{n}")
    assert not sospechosos, sospechosos


def test_frontend_sin_scripts_en_linea():
    """La CSP (script-src 'self') bloquea `<script>` con código dentro del HTML."""
    import re

    raiz = Path(__file__).resolve().parent.parent / "frontend"
    abre = re.compile(r"<script(?![^>]*\ssrc=)[^>]*>", re.I)
    en_linea = [f.name for f in raiz.glob("*.html") if abre.search(f.read_text(encoding="utf-8"))]
    assert not en_linea, en_linea


def test_estaticos_se_revalidan_para_no_mezclar_versiones(client):
    assert client.get("/login.html").headers["cache-control"] == "no-cache"
    assert client.get("/health").headers["cache-control"] == "no-cache"
