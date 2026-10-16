"""Configuración de acceso a la base de datos SQLite local.

Configuración centralizada de SQLAlchemy para la persistencia local de la
aplicación de escritorio. Se desacopla por completo de cualquier servicio
externo: toda la persistencia ocurre en un archivo SQLite local.
"""

import os
import sys

from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


# ------------------------------------------------------------------
# Ruta absoluta a la base de datos (crítico para PyInstaller)
# ------------------------------------------------------------------
# PyInstaller empaqueta la app en un único .exe; en modo compilado
# (`sys.frozen` es True) el "directorio actual" (CWD) no es fiable (p. ej.
# `%SystemRoot%\System32` al lanzarse por doble clic). Por eso, compilado se
# tomaba como base la carpeta donde reside el ejecutable (%~dp0), lo que en
# entornos empaquetados puede caer en un directorio de solo lectura
# (p. ej. `Program Files` con NSIS).
#
# PRECEDENCIA (de mayor a menor):
#   1. `USER_DATA_DIR`: el proceso principal de Electron (electron/main.js)
#      inyecta aquí `app.getPath('userData')` de forma segura y escribible
#      (`%APPDATA%\<nombre>`); en producción `pos_local.db` se crea ahí.
#   2. `sys.frozen` (exe) y NO hay variable: se mantiene el viejo
#      comportamiento junto al ejecutable (retrocompatibilidad).
#   3. Modo desarrollo / código fuente: directorio actual (como hasta ahora).
def _db_base_dir() -> str:
    user_data = os.environ.get("USER_DATA_DIR", "").strip()
    if user_data:
        # Aseguramos que el directorio exista antes de intentar escribir.
        os.makedirs(user_data, exist_ok=True)
        return user_data

    if getattr(sys, "frozen", False):
        # Aplicación compilada con PyInstaller: %~dp0 del ejecutable.
        return os.path.dirname(os.path.abspath(sys.executable))
    # Modo desarrollo / código fuente.
    return os.getcwd()


# Directorio destino y nombre del archivo de BD.
_DB_DIR = _db_base_dir()
os.makedirs(_DB_DIR, exist_ok=True)  # idempotente: si existe no falla
_DB_PATH = os.path.join(_DB_DIR, "pos_local.db")

# En las URLs de SQLite conviene usar "/" como separador (portable entre SO;
# SQLAlchemy acepta tanto `C:/...` como `C:\...`, pero "/" es el más robusto).
_SQLITE_PATH = _DB_PATH.replace("\\", "/")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{_SQLITE_PATH}"

# --- Engine ----------------------------------------------------------------
# `check_same_thread=False` es CRÍTICO en FastAPI/SQLite: SQLAlchemy puede
# abrir conexiones desde distintos hilos (threadpool de endpoints). Sin este
# parámetro, SQLite lanza `sqlite3.ProgrammingError` al compartir conexiones
# entre hilos.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _configurar_sqlite(dbapi_conn, _record) -> None:
    """Pragmas de cada conexión nueva.

    - WAL: lectores y escritor no se bloquean entre sí (reportes mientras se
      vende) y la base resiste mejor un corte de luz a mitad de escritura.
    - busy_timeout: si la base está ocupada, espera hasta 5 s en vez de fallar
      al instante con "database is locked".
    El modo de sincronización queda en su valor por defecto (FULL): cada venta
    confirmada está en disco.
    """
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()

# --- SessionLocal ----------------------------------------------------------
# `autocommit=False`: las transacciones no se confirman silenciosamente; hay
# que llamar explícitamente a `commit()`.
# `autoflush=False`: no se fuerza la sincronización de cambios pendientes a la
# BD antes de cada consulta; se controla manualmente, mejorando rendimiento
# y previsibilidad.
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# --- Base declarativa ------------------------------------------------------
# Clase base para todos los modelos ORM. Cada modelo la hereda y las tablas
# se crean automáticamente al importarlas con `Base.metadata.create_all(engine)`.
Base = declarative_base()


def get_db():
    """Dependencia generadora de inyección de dependencias.

    Abre una nueva sesión por request, garantiza el cierre (rollback implícito
    si no se confirma) y la entrega al endpoint de FastAPI. Uso:

        @app.get("/items")
        def read_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
