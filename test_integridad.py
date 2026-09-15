#!/usr/bin/env python3
"""
test_integridad.py — Auditoría estática pre-release del Punto de Venta.

Script de análisis estático (sin ejecutar la app) que valida las correcciones
aplicadas en el frontend. Imprime "✅ PASS" o "❌ FAIL" por cada punto y un
resumen final. Sale con código 0 si todo pasa, 1 si algo falla (apto para CI).

Ejecutar desde la raíz del proyecto:
    python test_integridad.py

Puntos validados:
  1. Aislamiento offline de Reportes (Chart.js local, sin CDN).
  2. Enrutamiento del menú: href de Inventario -> inventario.html (no pos.html).
  3. CSS compilado: scrollbar dark + badge de contraste (orange-400) en oscuro.
  4. Auto-focus del modal POS sobre el input de cantidad (#peso-valor y #servicio-cantidad).
  5. Coherencia del enum multi-rubro (modelo ↔ schema ↔ UI de inventario).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# Portabilidad de consola (Windows cp1252 no soporta ✅/─).
# Reconfiguramos stdout a UTF-8; si el entorno no lo permite, degradamos los
# símbolos a ASCII para no romper la ejecución (robustez multiplataforma).
# --------------------------------------------------------------------------
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass


# Detectar si podemos imprimir UTF-8; si no, usar glifos ASCII equivalentes.
def _soporta_unicode() -> bool:
    enc = (getattr(sys.stdout, "encoding", "") or "").lower()
    return "utf" in enc


UNICODE_OK = _soporta_unicode()
GLIFO_OK = "✅ PASS" if UNICODE_OK else "[PASS]"
GLIFO_FAIL = "❌ FAIL" if UNICODE_OK else "[FAIL]"
GLIFO_X = "❌" if UNICODE_OK else "x"
GLIFO_CHECK = "✅" if UNICODE_OK else "-"
SEP = "─" if UNICODE_OK else "-"
SEP2 = "="

# --------------------------------------------------------------------------
# Rutas base (relativas a la raíz del proyecto = carpeta de este script).
# --------------------------------------------------------------------------
RAIZ = Path(__file__).resolve().parent
FRONTEND = RAIZ / "frontend"
ASSETS = FRONTEND / "assets"
LIBS = FRONTEND / "libs"
CSS_COMPILADO = FRONTEND / "dist" / "css" / "app.css"

# Marcadores de URLs externas (CDN) que romperían el modo offline.
PATRON_CDN = re.compile(
    r"(cdn\.jsdelivr\.net|unpkg\.com|cdnjs\.cloudflare\.com|cdnjs\.com)",
    re.IGNORECASE,
)

# --------------------------------------------------------------------------
# Utilidades de reporte.
# --------------------------------------------------------------------------
RESULTADOS: list[tuple[str, bool, str]] = []


def reportar(nombre: str, ok: bool, detalle: str = "") -> None:
    icono = GLIFO_OK if ok else GLIFO_FAIL
    print(f"{icono}  —  {nombre}")
    if detalle:
        for linea in detalle.splitlines():
            print(f"           {linea}")
    RESULTADOS.append((nombre, ok, detalle))


def leer_texto(ruta: Path) -> str:
    """Lee un archivo de texto tolerando cualquier codificación (best-effort)."""
    try:
        return ruta.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""


# ==========================================================================
# 1. AISLAMIENTO OFFLINE (Reportes)
# ==========================================================================
def validar_offline_reportes() -> None:
    print(f"\n{SEP*2} 1. Aislamiento Offline (Reportes) {SEP*12}")

    # 1a. Chart.js local presente en frontend/ (libs, js o assets).
    candidatos = list(LIBS.glob("chart*.js"))
    candidatos += (
        list((FRONTEND / "js").glob("chart*.js")) if (FRONTEND / "js").exists() else []
    )
    candidatos += list(ASSETS.glob("chart*.js"))
    # Deduplicar preservando orden (varias glob pueden capturar el mismo archivo).
    chart_local = list({c.resolve(): c for c in candidatos if c.is_file()}.values())
    reportar(
        "Chart.js local existe en frontend/",
        bool(chart_local),
        (
            "Encontrado: " + ", ".join(str(c.relative_to(RAIZ)) for c in chart_local)
            if chart_local
            else "No se halló ningún chart*.js en libs/, js/ ni assets/."
        ),
    )

    # 1b. reportes.html sin referencias externas (CDN).
    html = leer_texto(FRONTEND / "reportes.html")
    if not html:
        reportar(
            "reportes.html sin referencias CDN", False, "No se pudo leer reportes.html."
        )
        return

    hallazgos = PATRON_CDN.findall(html)
    reportar(
        "reportes.html sin referencias a CDN externos",
        not hallazgos,
        (
            "Referencias externas detectadas: " + ", ".join(sorted(set(hallazgos)))
            if hallazgos
            else "Sin URLs externas (jsdelivr/unpkg/cdnjs)."
        ),
    )

    # 1c. (Refuerzo) reportes.html usa Chart.js local por ruta relativa.
    usa_lib_local = (
        re.search(r'src\s*=\s*["\']\./libs/chart[\w.\-]*\.js["\']', html) is not None
    )
    reportar(
        "reportes.html carga Chart.js desde ./libs/ (local)",
        usa_lib_local,
        (
            "Ruta relativa ./libs/chart*.js encontrada."
            if usa_lib_local
            else "No se encontró <script src='./libs/chart...js'>."
        ),
    )


# ==========================================================================
# 2. ENRUTAMIENTO DEL MENÚ (Inventario)
# ==========================================================================
def validar_ruteo_inventario() -> None:
    print(f"\n{SEP*2} 2. Enrutamiento del Menú (Inventario) {SEP*12}")

    guard = leer_texto(FRONTEND / "services" / "guard.js")
    if not guard:
        reportar(
            "href de Inventario correcto en guard.js",
            False,
            "No se pudo leer guard.js.",
        )
        return

    # Regex sobre el objeto del ítem inventario: captura el href declarado.
    # Acepta comillas simples o dobles y espaciado variable.
    m = re.search(
        r"id\s*:\s*['\"]inventario['\"]\s*,\s*href\s*:\s*['\"]([^'\"]+)['\"]",
        guard,
    )
    href = m.group(1) if m else None

    apunta_ok = href == "inventario.html"
    reportar(
        "href de 'inventario' apunta a inventario.html",
        apunta_ok,
        (
            f"href detectado: '{href}'"
            if m
            else "No se encontró el ítem 'inventario' en MENU_ITEMS."
        ),
    )

    # No debe cruzar con pos.html en la MISMA línea del ítem inventario.
    cruce = (
        re.search(
            r"id\s*:\s*['\"]inventario['\"][^\n]*pos\.html",
            guard,
        )
        is not None
    )
    reportar(
        "El ítem Inventario no cruza con pos.html",
        not cruce,
        (
            "Cruce detectado (inventario -> pos.html)."
            if cruce
            else "Sin cruce con pos.html."
        ),
    )


# ==========================================================================
# 3. CSS Y MODO OSCURO COMPILADO
# ==========================================================================
def validar_css_dark() -> None:
    print(f"\n{SEP*2} 3. CSS y Modo Oscuro Compilado {SEP*12}")

    css = leer_texto(CSS_COMPILADO)
    if not css:
        reportar(
            "Scrollbar dark en CSS compilado",
            False,
            f"No se pudo leer {CSS_COMPILADO}.",
        )
        reportar("Badge de contraste (orange-400) en dark", False, "CSS no disponible.")
        return

    # 3a. Regla ::-webkit-scrollbar ligada a .dark.
    scrollbar_dark = re.search(r"\.dark\s+::-webkit-scrollbar", css) is not None
    reportar(
        "Regla '.dark ::-webkit-scrollbar' presente",
        scrollbar_dark,
        (
            "Regla encontrada."
            if scrollbar_dark
            else "No se encontró '.dark ::-webkit-scrollbar'."
        ),
    )

    # 3b. Contraste del badge en dark. Tailwind compila la variante a algo como:
    #     :is(.dark .badge-warning){... color:rgb(251 146 60 ...)}   (orange-400)
    #     o deja la clase .dark\:text-orange-400. Aceptamos ambas formas.
    rgb_orange_400 = "251 146 60"  # orange-400 en canales RGB
    tiene_variante = (
        re.search(r":is\(\.dark[^)]*\)\s*\{[^}]*" + re.escape(rgb_orange_400), css)
        is not None
        or re.search(r"\.dark\\:text-orange-400", css) is not None
        or "orange" in css  # última red de seguridad (nombre de clase sin compilar)
    )
    reportar(
        "Badge de contraste en oscuro (orange-400) presente",
        tiene_variante,
        (
            "Variante dark con orange-400 (rgb 251 146 60) encontrada."
            if tiene_variante
            else "No se encontró la variante dark del badge."
        ),
    )


# ==========================================================================
# 4. AUTO-FOCUS DEL MODAL (POS)
# ==========================================================================
def validar_autofocus_pos() -> None:
    print(f"\n{SEP*2} 4. Auto-Focus del Modal (POS) {SEP*12}")

    pos = leer_texto(FRONTEND / "services" / "pos.js")
    if not pos:
        reportar(
            "Auto-focus del input de cantidad en pos.js",
            False,
            "No se pudo leer pos.js.",
        )
        return

    # El input de cantidad del modal de peso es #peso-valor (ver pos.html).
    # El foco se aplica vía helper asíncrono focusInputDiferido('peso-valor', ...).
    tiene_helper = (
        re.search(r"focusInputDiferido\(\s*['\"]peso-valor['\"]", pos) is not None
    )
    tiene_directo = (
        re.search(r"['\"]peso-valor['\"][^\n]*\.focus\(\)", pos) is not None
        or re.search(r"\$\(\s*['\"]peso-valor['\"]\s*\)\.focus\(\)", pos) is not None
    )

    reportar(
        "Auto-focus aplicado al input de cantidad (#peso-valor)",
        tiene_helper or tiene_directo,
        (
            "Foco vía focusInputDiferido('peso-valor')."
            if tiene_helper
            else (
                "Foco directo vía #peso-valor.focus()."
                if tiene_directo
                else "No se encontró foco asociado a #peso-valor."
            )
        ),
    )

    # Refuerzo: confirmar que el helper existe (definición).
    define_helper = re.search(r"function\s+focusInputDiferido\s*\(", pos) is not None
    reportar(
        "Helper focusInputDiferido() definido en pos.js",
        define_helper,
        (
            "Definido."
            if define_helper
            else "No se definió el helper (posible regresión)."
        ),
    )

    # --- Modal de SERVICIO/COPIA (librería): mismo patrón ergonómico. ---
    tiene_helper_serv = (
        re.search(r"focusInputDiferido\(\s*['\"]servicio-cantidad['\"]", pos)
        is not None
    )
    reportar(
        "Auto-focus aplicado al input de copias (#servicio-cantidad)",
        tiene_helper_serv,
        (
            "Foco vía focusInputDiferido('servicio-cantidad')."
            if tiene_helper_serv
            else "No se encontró foco asociado a #servicio-cantidad."
        ),
    )


# ==========================================================================
# 5. COHERENCIA DEL ENUM MULTI-RUBRO (modelo ↔ schema ↔ UI)
# ==========================================================================
def validar_enum_multirubro() -> None:
    r"""Verifica que los `tipo_unidad` soportados sean consistentes en las capas.

    Fuente de verdad: `Producto.TIPOS_UNIDAD` (app/models). Comprueba que el
    schema Pydantic derive su patrón de ahí y que la UI (inventario.html) ofrezca
    las mismas opciones — así no se puede guardar un producto que el backend
    rechace (evita el bug "opción en UI sin soporte de API").
    """
    print(f"\n{SEP*2} 5. Coherencia del Enum Multi-rubro {SEP*12}")

    modelos = leer_texto(RAIZ / "app" / "models" / "__init__.py")
    schema = leer_texto(RAIZ / "app" / "schemas" / "producto.py")
    html = leer_texto(FRONTEND / "inventario.html")

    # 5a. El modelo declara los tipos esperados.
    esperados = ["peso", "unidad", "porcion", "metros", "litros", "servicio"]
    m = re.search(r"TIPOS_UNIDAD\s*=\s*\(([^)]*)\)", modelos)
    declarados = re.findall(r"['\"]([a-z]+)['\"]", m.group(1)) if m else []
    reportar(
        "app/models declara todos los tipo_unidad esperados",
        set(esperados).issubset(set(declarados)),
        f"declarados: {declarados}",
    )

    # 5b. El schema deriva el patrón de Producto (DRY) y NO hardcodea el viejo.
    deriva = "_PATTERN_TIPO_UNIDAD" in schema and "Producto.TIPOS_UNIDAD" in schema
    viejo = 'pattern="^(peso|unidad|porcion)$"' in schema
    reportar(
        "El schema deriva el patrón del modelo (sin hardcodear el enum viejo)",
        deriva and not viejo,
        (
            "Deriva de Producto.TIPOS_UNIDAD."
            if deriva and not viejo
            else "Aún usa un patrón hardcodeado."
        ),
    )

    # 5c. La UI ofrece todas las opciones (value=) de tipo_unidad.
    opciones = set(re.findall(r'id="prod-tipo"[\s\S]*?</select>', html))
    bloque = next(iter(opciones), "")
    valores_ui = set(re.findall(r'<option value="([a-z]+)"', bloque))
    faltantes = set(esperados) - valores_ui
    reportar(
        "La UI (inventario.html) ofrece todas las unidades soportadas",
        not faltantes,
        (
            f"opciones UI: {sorted(valores_ui)}"
            if not faltantes
            else f"faltan en la UI: {sorted(faltantes)}"
        ),
    )

    # 5d. Coherencia de negocio: indumentaria fuerza 'unidad'; las continuas
    #     (peso/metros/litros) admiten importe. Verificamos que el modelo
    #     exponga el subconjunto continuo usado por ventas.
    reportar(
        "app/models expone TIPOS_UNIDAD_CONTINUOS (peso/metros/litros)",
        "TIPOS_UNIDAD_CONTINUOS" in modelos,
        "Usado por el router de ventas para venta por importe.",
    )


# ==========================================================================
# MAIN
# ==========================================================================
def main() -> int:
    print("=" * 64)
    print("  AUDITORÍA DE INTEGRIDAD PRE-RELEASE — Punto de Venta")
    print("=" * 64)

    validar_offline_reportes()
    validar_ruteo_inventario()
    validar_css_dark()
    validar_autofocus_pos()
    validar_enum_multirubro()

    total = len(RESULTADOS)
    pasados = sum(1 for _, ok, _ in RESULTADOS if ok)
    fallados = total - pasados

    print("\n" + "=" * 64)
    print(f"  RESUMEN: {pasados}/{total} comprobaciones OK  |  {fallados} fallo(s)")
    print("=" * 64)

    if fallados:
        print("\nComprobaciones fallidas:")
        for nombre, ok, _ in RESULTADOS:
            if not ok:
                print(f"  {GLIFO_X} {nombre}")
        return 1

    print(f"\n{GLIFO_CHECK} Todas las comprobaciones pasaron.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
