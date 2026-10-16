"""Pruebas de licencias (VX1/VX2), anti-repetición, alta con cliente_id y
recuperación de contraseña por código firmado.

Se llama `test_zz_*` para correr DESPUÉS de test_setup_alta.py, con el que
comparte la base temporal. Si se corre solo, crea su propio administrador.
"""

import json
import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

os.environ.setdefault("USER_DATA_DIR", tempfile.mkdtemp(prefix="pos_test_"))
for _var in ("SECRET_KEY", "ADMIN_PASSWORD", "ADMIN_EMAIL", "ENV", "CORS_ORIGINS"):
    os.environ.pop(_var, None)

import pytest  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: E402
    Ed25519PrivateKey,
)
from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Licencia, Usuario, now_utc  # noqa: E402
from app.services import hora_externa, licencia_firma, licencia_service  # noqa: E402
from app.services.licencia_firma import (  # noqa: E402
    calcular_huella,
    firmar_alta,
    firmar_licencia,
    firmar_recuperacion,
    verificar_alta,
    verificar_licencia,
    verificar_recuperacion,
)

ADMIN_EMAIL = "admin-lic@comercio.test"
ADMIN_PASS = "clave-admin-lic-123"
FUTURO = date(2035, 1, 1)
PASADO = date(2020, 1, 1)


@pytest.fixture(scope="module")
def llaves(tmp_path_factory):
    privada = Ed25519PrivateKey.generate()
    pem = privada.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    ruta = tmp_path_factory.mktemp("llaves2") / "licencia_public.key"
    ruta.write_bytes(pem)
    original = licencia_firma.RUTA_PUBLICA_DEFECTO
    licencia_firma.RUTA_PUBLICA_DEFECTO = ruta
    licencia_service._cache_vigencia.clear()
    yield privada
    licencia_firma.RUTA_PUBLICA_DEFECTO = original
    licencia_service._cache_vigencia.clear()


@pytest.fixture(autouse=True)
def sin_internet(monkeypatch):
    """Las pruebas no dependen de la red: la hora externa siempre falla."""
    monkeypatch.setattr(hora_externa, "_consultar_hora_externa", lambda: None)
    hora_externa._cache.update({"fecha": None, "obtenida_en": None, "fallo_en": None})


@pytest.fixture(scope="module")
def client(llaves):
    with TestClient(app) as c:
        yield c


def _huella() -> str:
    db = SessionLocal()
    try:
        lic = db.query(Licencia).first()
        return calcular_huella(lic.cliente_id if lic and lic.cliente_id else "demo")
    finally:
        db.close()


@pytest.fixture(scope="module")
def admin(client, llaves):
    """Encabezados de un administrador (lo crea si la base está vacía)."""
    if client.get("/api/setup/estado").json()["necesita_setup"]:
        r = client.post(
            "/api/setup/inicializar",
            json={
                "codigo_alta": firmar_alta(llaves, _huella()),
                "nombre": "Admin Lic",
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASS,
            },
        )
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.post(
        "/api/auth/login",
        data={"username": "pedro@libreria.com", "password": "clave-segura-123"},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _activar(client, admin, codigo):
    return client.post(
        "/api/licencia/activar", headers=admin, json={"codigo_firmado": codigo}
    )


def _estado(client, admin) -> dict:
    return client.get("/api/licencia/estado", headers=admin).json()


# ---------------------------------------------------------------------------
# Firma: huella, compatibilidad y tipos de código
# ---------------------------------------------------------------------------
def test_huella_de_16_y_codigos_viejos_de_8_siguen_valiendo(llaves):
    huella = calcular_huella("demo")
    hash16 = huella.split("-")[1]
    assert len(hash16) == 16

    publica = llaves.public_key()
    # VX1 con el hash de 8 (como los ya entregados a clientes).
    viejo = firmar_licencia(llaves, "demo", hash16[:8], FUTURO)
    r = verificar_licencia(publica, viejo, huella)
    assert r.valido and r.serie is None and r.fecha_vencimiento == FUTURO
    # VX1 con el hash completo y VX2 con serie.
    assert verificar_licencia(publica, firmar_licencia(llaves, "demo", huella, FUTURO), huella).valido
    nuevo = firmar_licencia(llaves, "demo", huella, FUTURO, serie=123)
    assert nuevo.startswith("VX2.")
    assert verificar_licencia(publica, nuevo, huella).serie == 123

    # Un hash demasiado corto, o de otra PC, no vale.
    assert not verificar_licencia(publica, firmar_licencia(llaves, "demo", hash16[:4], FUTURO), huella).valido
    assert not verificar_licencia(publica, firmar_licencia(llaves, "demo", "POS-DEADBEEF11112222-DEMO", FUTURO), huella).valido


def test_un_codigo_no_se_puede_reinterpretar_como_otro_tipo(llaves):
    publica = llaves.public_key()
    huella = calcular_huella("demo")
    alta = firmar_alta(llaves, huella)
    rec = firmar_recuperacion(llaves, huella, 1, FUTURO)
    lic2 = firmar_licencia(llaves, "demo", huella, FUTURO, serie=5)
    # Cambiar el prefijo no engaña: el tipo va dentro de lo firmado.
    assert not verificar_licencia(publica, "VX1." + alta.split(".", 1)[1], huella).valido
    assert not verificar_licencia(publica, "VX2." + rec.split(".", 1)[1], huella).valido
    assert not verificar_alta(publica, "VXA." + lic2.split(".", 1)[1], huella).valido
    assert not verificar_recuperacion(publica, "VXR." + alta.split(".", 1)[1], huella).valido
    # Y una firma ajena nunca vale.
    ajena = firmar_recuperacion(Ed25519PrivateKey.generate(), huella, 1, FUTURO)
    assert not verificar_recuperacion(publica, ajena, huella).valido


# ---------------------------------------------------------------------------
# Activación: anti-repetición y vigencia tomada de la firma
# ---------------------------------------------------------------------------
def test_activacion_vx2_no_acepta_series_viejas(client, admin, llaves):
    h = _huella()
    c100 = firmar_licencia(llaves, "demo", h, FUTURO, serie=100)
    c50 = firmar_licencia(llaves, "demo", h, FUTURO, serie=50)
    c200 = firmar_licencia(llaves, "demo", h, FUTURO, serie=200)

    assert _activar(client, admin, c100).status_code == 200
    assert _estado(client, admin)["bloqueada"] is False
    # Repetir el mismo código no es error; uno más viejo sí se rechaza.
    again = _activar(client, admin, c100)
    assert again.status_code == 200 and "ya estaba activa" in again.json()["mensaje"]
    viejo = _activar(client, admin, c50)
    assert viejo.status_code == 400 and "más viejo" in viejo.json()["detail"]
    assert _activar(client, admin, c200).status_code == 200


def test_editar_la_base_no_extiende_ni_revive_la_licencia(client, admin, llaves):
    h = _huella()
    vencida = firmar_licencia(llaves, "demo", h, PASADO, dias_gracia=0, serie=300)
    assert _activar(client, admin, vencida).status_code == 200
    assert _estado(client, admin)["bloqueada"] is True

    # Alguien edita la columna de vencimiento en SQLite: no cambia nada.
    db = SessionLocal()
    try:
        lic = db.query(Licencia).first()
        lic.fecha_vencimiento = datetime(2099, 1, 1)
        lic.dias_gracia = 9999
        db.commit()
    finally:
        db.close()
    assert _estado(client, admin)["bloqueada"] is True

    # Un código guardado que ya no verifica bloquea con un mensaje claro.
    db = SessionLocal()
    try:
        db.query(Licencia).first().codigo_activacion = "VX2.basura.basura"
        db.commit()
    finally:
        db.close()
    est = _estado(client, admin)
    assert est["bloqueada"] is True and "no es válida" in est["mensaje"]

    # Una renovación firmada lo arregla.
    assert _activar(client, admin, firmar_licencia(llaves, "demo", h, FUTURO, serie=400)).status_code == 200
    assert _estado(client, admin)["bloqueada"] is False


def test_codigo_vx1_original_sigue_funcionando_sin_retroceder(client, admin, llaves):
    h = _huella()
    # Ya hay una licencia por código hasta FUTURO: un VX1 más corto retrocede.
    corto = firmar_licencia(llaves, "demo", h, date(2030, 1, 1))
    r = _activar(client, admin, corto)
    assert r.status_code == 400 and "vence antes" in r.json()["detail"]
    largo = firmar_licencia(llaves, "demo", h, date(2040, 1, 1))
    assert _activar(client, admin, largo).status_code == 200
    assert _estado(client, admin)["bloqueada"] is False


# ---------------------------------------------------------------------------
# Demo anclada fuera de la base
# ---------------------------------------------------------------------------
def test_borrar_la_licencia_no_regala_otra_demo(client, admin, llaves):
    ancla = licencia_service._ruta_ancla()
    ancla_original = ancla.read_text(encoding="utf-8") if ancla.exists() else None

    def escribir_ancla(inicio: datetime):
        iso = inicio.replace(microsecond=0).isoformat()
        ancla.write_text(
            json.dumps({"inicio": iso, "sello": licencia_service._sello(iso)}),
            encoding="utf-8",
        )

    def borrar_fila():
        db = SessionLocal()
        try:
            db.query(Licencia).delete()
            db.commit()
        finally:
            db.close()

    try:
        # Instalada hace 100 días: la demo (30 + 3 de gracia) ya terminó.
        escribir_ancla(now_utc() - timedelta(days=100))
        borrar_fila()
        db = SessionLocal()
        try:
            assert licencia_service.evaluar(db).bloqueada is True
        finally:
            db.close()

        # Ancla adulterada (sello inválido): también se trata como vencida.
        ancla.write_text(
            json.dumps({"inicio": "2999-01-01T00:00:00", "sello": "0" * 64}),
            encoding="utf-8",
        )
        borrar_fila()
        db = SessionLocal()
        try:
            assert licencia_service.evaluar(db).bloqueada is True
        finally:
            db.close()

        # Instalación recién hecha: demo vigente.
        escribir_ancla(now_utc())
        borrar_fila()
        db = SessionLocal()
        try:
            est = licencia_service.evaluar(db)
            assert est.bloqueada is False and est.dias_restantes >= 28
        finally:
            db.close()
    finally:
        if ancla_original is not None:
            ancla.write_text(ancla_original, encoding="utf-8")
    # Se deja una licencia firmada vigente para el resto de las pruebas.
    assert _activar(client, admin, firmar_licencia(llaves, "demo", _huella(), FUTURO, serie=10**10)).status_code == 200


# ---------------------------------------------------------------------------
# Recuperación de contraseña
# ---------------------------------------------------------------------------
def _login_codigo(client, email, password) -> int:
    return client.post(
        "/api/auth/login", data={"username": email, "password": password}
    ).status_code


def _usuario_admin_email() -> str:
    db = SessionLocal()
    try:
        return db.query(Usuario).filter(Usuario.rol == "admin").order_by(Usuario.id).first().email
    finally:
        db.close()


def _recuperar(client, codigo, email, password="nueva-clave-456"):
    return client.post(
        "/api/setup/recuperar",
        json={"codigo": codigo, "email": email, "password": password},
    )


def test_recuperacion_de_contrasena_con_codigo_firmado(client, admin, llaves):
    from app.routers import setup as rs

    rs._guardia_recuperacion.registrar_exito(rs._CLAVE_RECUPERACION)
    email = _usuario_admin_email()
    h = client.get("/api/setup/huella").json()["huella"]
    assert h == _huella()
    hoy = now_utc().date()
    base = int(datetime.now().timestamp())

    # Sin código válido no cambia nada.
    for malo in (
        "VXR.xxxxxxxxxx.yyyy",
        firmar_recuperacion(Ed25519PrivateKey.generate(), h, base, hoy + timedelta(days=2)),
        firmar_recuperacion(llaves, "POS-DEADBEEF11112222-DEMO", base, hoy + timedelta(days=2)),
        firmar_recuperacion(llaves, h, base, hoy - timedelta(days=1)),  # vencido
        firmar_recuperacion(llaves, h, base, hoy + timedelta(days=2), email="otro@x.com"),
    ):
        assert _recuperar(client, malo, email).status_code == 400
    rs._guardia_recuperacion.registrar_exito(rs._CLAVE_RECUPERACION)

    # Una cuenta de cajero no se recupera por esta vía.
    codigo = firmar_recuperacion(llaves, h, base, hoy + timedelta(days=2))
    db = SessionLocal()
    try:
        cajero = db.query(Usuario).filter(Usuario.rol == "cajero").first()
        cajero_email = cajero.email if cajero else None
    finally:
        db.close()
    if cajero_email:
        assert _recuperar(client, codigo, cajero_email).status_code == 400
        rs._guardia_recuperacion.registrar_exito(rs._CLAVE_RECUPERACION)

    # Código bueno: cambia la contraseña, la vieja deja de servir.
    ok = _recuperar(client, codigo, email)
    assert ok.status_code == 200, ok.text
    assert _login_codigo(client, email, "nueva-clave-456") == 200

    # No se puede repetir ni usar uno más viejo.
    assert _recuperar(client, codigo, email, "otra-clave-789").status_code == 400
    viejo = firmar_recuperacion(llaves, h, base - 100, hoy + timedelta(days=2))
    assert _recuperar(client, viejo, email, "otra-clave-789").status_code == 400
    rs._guardia_recuperacion.registrar_exito(rs._CLAVE_RECUPERACION)

    # Un administrador bloqueado por intentos fallidos queda libre tras recuperar.
    for _ in range(5):
        _login_codigo(client, email, "mal-mal-mal")
    assert _login_codigo(client, email, "nueva-clave-456") == 429
    nuevo = firmar_recuperacion(llaves, h, base + 5, hoy + timedelta(days=2), email=email)
    assert _recuperar(client, nuevo, email, "clave-final-789").status_code == 200
    assert _login_codigo(client, email, "clave-final-789") == 200

    # Se deja la contraseña original para no afectar a otras pruebas.
    ult = firmar_recuperacion(llaves, h, base + 10, hoy + timedelta(days=2), email=email)
    original = ADMIN_PASS if email == ADMIN_EMAIL else "clave-segura-123"
    assert _recuperar(client, ult, email, original).status_code == 200


def test_recuperacion_limita_los_intentos(client):
    from app.routers import setup as rs

    rs._guardia_recuperacion.registrar_exito(rs._CLAVE_RECUPERACION)
    email = _usuario_admin_email()
    for _ in range(5):
        assert _recuperar(client, "VXR.xxxxxxxxxx.yyyy", email).status_code == 400
    bloqueado = _recuperar(client, "VXR.xxxxxxxxxx.yyyy", email)
    assert bloqueado.status_code == 429 and int(bloqueado.headers["retry-after"]) > 0
    rs._guardia_recuperacion.registrar_exito(rs._CLAVE_RECUPERACION)


# ---------------------------------------------------------------------------
# Alta REMOTA: el código fija el cliente_id
# ---------------------------------------------------------------------------
def test_alta_puede_fijar_el_cliente_id(client, llaves, monkeypatch):
    from app.routers import setup as rs

    assert verificar_alta(
        llaves.public_key(),
        firmar_alta(llaves, _huella(), cliente_id=" Libreria-Pedro "),
        _huella(),
    ).cliente_id == "libreria-pedro"

    # Simula una instalación vacía sin tocar los usuarios reales.
    monkeypatch.setattr(rs, "_sin_usuarios", lambda db: True)
    invalido = firmar_alta(llaves, _huella(), cliente_id="x")  # demasiado corto
    r = client.post(
        "/api/setup/inicializar",
        json={"codigo_alta": invalido, "nombre": "N", "email": "n1@x.com", "password": "12345678"},
    )
    assert r.status_code == 400

    valido = firmar_alta(llaves, _huella(), rubro="ferreteria", cliente_id="ferreteria-lopez")
    r = client.post(
        "/api/setup/inicializar",
        json={"codigo_alta": valido, "nombre": "Lopez", "email": "lopez@x.com", "password": "12345678"},
    )
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        assert db.query(Licencia).first().cliente_id == "ferreteria-lopez"
        # La huella cambia con el cliente_id (hay que emitir la licencia con la nueva).
        assert calcular_huella("ferreteria-lopez") != calcular_huella("demo")
        # Limpieza: vuelve a la instalación de prueba original.
        db.query(Licencia).first().cliente_id = "demo"
        db.query(Usuario).filter(Usuario.email == "lopez@x.com").delete()
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Hora externa: sin internet no se insiste en cada consulta
# ---------------------------------------------------------------------------
def test_sin_internet_se_consulta_la_hora_una_sola_vez(monkeypatch):
    llamadas = []
    monkeypatch.setattr(
        hora_externa, "_consultar_hora_externa", lambda: llamadas.append(1)
    )
    hora_externa._cache.update({"fecha": None, "obtenida_en": None, "fallo_en": None})
    for _ in range(5):
        f = hora_externa.resolver_fecha_actual(None)
        assert f.fuente in ("reloj_local", "delta_local")
    assert len(llamadas) == 1
    assert hora_externa.URL_HORA_PRIMARIA.startswith("https://")


# ---------------------------------------------------------------------------
# Huella v2 (identificadores de Windows) con compatibilidad hacia atrás
# ---------------------------------------------------------------------------
def test_licencia_firmada_con_la_huella_original_sigue_valiendo(llaves):
    publica = llaves.public_key()
    original = f"POS-{licencia_firma._hash_legacy('demo')}-DEMO"
    aceptadas = licencia_firma.huellas_aceptadas("demo")
    assert original in aceptadas
    # Las tres clases de código firmadas con la huella original valen.
    assert verificar_licencia(publica, firmar_licencia(llaves, "demo", original, FUTURO, serie=7), aceptadas).valido
    assert verificar_licencia(publica, firmar_licencia(llaves, "demo", original, FUTURO), aceptadas).valido
    assert verificar_alta(publica, firmar_alta(llaves, original), aceptadas).valido
    assert verificar_recuperacion(publica, firmar_recuperacion(llaves, original, 1, FUTURO), aceptadas).valido
    # Y una huella ajena sigue sin valer.
    ajena = "POS-DEADBEEF11112222-DEMO"
    assert not verificar_licencia(publica, firmar_licencia(llaves, "demo", ajena, FUTURO, serie=8), aceptadas).valido


def test_huella_v2_depende_de_las_senales_de_windows(monkeypatch):
    base = calcular_huella("demo")
    if not licencia_firma._senales_hardware_v2():
        pytest.skip("Sin identificadores de Windows: la huella queda en formato original")
    assert base != f"POS-{licencia_firma._hash_legacy('demo')}-DEMO"
    # Otro MachineGuid => otra huella (clonar MAC y nombre ya no alcanza).
    licencia_firma._senales_hardware_v2.cache_clear()
    monkeypatch.setattr(licencia_firma, "_senales_hardware_v2", lambda: ("guid:otro", "vol:00000001"))
    assert calcular_huella("demo") != base


# ---------------------------------------------------------------------------
# Fallo del control de licencia: cerrado con tolerancia de 72 h
# ---------------------------------------------------------------------------
def test_fallo_del_control_tolera_72h_y_luego_bloquea():
    licencia_service.registrar_control_ok()
    t0 = 1_800_000_000.0
    assert licencia_service.fallo_control_excedido(t0) is False  # primer fallo: se anota
    assert licencia_service.fallo_control_excedido(t0 + 71 * 3600) is False
    assert licencia_service.fallo_control_excedido(t0 + 73 * 3600) is True
    # Cuando el control vuelve a funcionar, el contador se reinicia.
    licencia_service.registrar_control_ok()
    assert licencia_service.fallo_control_excedido(t0 + 100 * 3600) is False
    licencia_service.registrar_control_ok()


def test_estado_de_fallo_alterado_cierra():
    licencia_service.registrar_control_ok()
    licencia_service._ruta_fallo().write_text("no es json", encoding="utf-8")
    assert licencia_service.fallo_control_excedido(1_800_000_000.0) is True
    licencia_service.registrar_control_ok()


def test_middleware_bloquea_escrituras_tras_72h_de_fallo(client, admin, monkeypatch):
    def roto(*a, **k):
        raise RuntimeError("falla simulada")

    monkeypatch.setattr("app.middleware.licencia.evaluar", roto)
    licencia_service.registrar_control_ok()
    # Dentro de la tolerancia se puede vender (no es un 402).
    r = client.post("/api/arqueo/abrir", headers=admin, json={"monto_inicial": 0})
    assert r.status_code != 402
    # Con el primer fallo anotado hace 73 h, se bloquea.
    licencia_service._ruta_fallo().write_text(
        json.dumps({"primero": __import__("time").time() - 73 * 3600}), encoding="utf-8"
    )
    r = client.post("/api/arqueo/abrir", headers=admin, json={"monto_inicial": 0})
    assert r.status_code == 402
    licencia_service.registrar_control_ok()


# ---------------------------------------------------------------------------
# Migraciones versionadas (Alembic)
# ---------------------------------------------------------------------------
def test_alembic_marca_la_base_y_es_idempotente(client):
    from sqlalchemy import text

    from app.migraciones_alembic import REVISION_BASE, aplicar_migraciones

    def revision():
        db = SessionLocal()
        try:
            return db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        finally:
            db.close()

    # El arranque de la app ya la marcó en la revisión base.
    assert revision() == REVISION_BASE
    # Correrlo de nuevo no rompe ni cambia nada (arranques sucesivos).
    aplicar_migraciones()
    assert revision() == REVISION_BASE
    # Una base de una versión anterior (sin tabla alembic_version) se adopta sin perder datos.
    db = SessionLocal()
    try:
        db.execute(text("DROP TABLE alembic_version"))
        db.commit()
        antes = db.execute(text("SELECT COUNT(*) FROM usuarios")).scalar()
    finally:
        db.close()
    aplicar_migraciones()
    assert revision() == REVISION_BASE
    db = SessionLocal()
    try:
        assert db.execute(text("SELECT COUNT(*) FROM usuarios")).scalar() == antes
    finally:
        db.close()


def test_licencia_vencida_tambien_bloquea_abonos_clientes_y_categorias():
    rb = licencia_service.requiere_bloqueo
    for ruta in ("/api/clientes", "/api/clientes/abc/abonos", "/api/categorias"):
        assert rb("POST", ruta), ruta
        assert not rb("GET", ruta), ruta  # consultar nunca se bloquea
    # Login, licencia y configuración siguen libres para poder regularizar.
    assert not rb("POST", "/api/auth/login")
    assert not rb("POST", "/api/licencia/activar")


def test_cantidades_absurdas_se_rechazan(client, admin):
    r = client.post(
        "/api/productos", headers=admin,
        json={"nombre": "Absurdo", "precio": "1e400", "stock": 1},
    )
    assert r.status_code == 422
    r = client.post(
        "/api/productos", headers=admin,
        json={"nombre": "Absurdo", "precio": 10, "stock": "1e400"},
    )
    assert r.status_code == 422
    r = client.patch("/api/productos/00000000-0000-0000-0000-000000000000/stock?cantidad=1e400", headers=admin)
    assert r.status_code == 422
