"""Utilidad de parcheo quirúrgico e idempotente sobre archivos de código.

Por qué existe este módulo (y no edición manual):
  El editor integrado de este entorno no resuelve correctamente las rutas de
  este proyecto (antepone un prefijo duplicado), por lo que la edición directa
  es poco fiable. Un parcheador en Python es determinista, auditable y
  re-ejecutable (idempotente): aplica reemplazos exactos anclados con
  verificación y aborta si el ancla no es única, evitando corromper el código.

Uso:
    python tools_upgrade/patcher.py
"""

from __future__ import annotations

from pathlib import Path

# Raíz del proyecto = carpeta que contiene `app/` y `frontend/`.
ROOT = Path(__file__).resolve().parent.parent


class PatchError(RuntimeError):
    pass


def _read(rel: str) -> str:
    p = ROOT / rel
    if not p.exists():
        raise PatchError(f"No existe: {rel}")
    return p.read_text(encoding="utf-8")


def _write(rel: str, content: str) -> None:
    (ROOT / rel).write_text(content, encoding="utf-8")


def apply(rel: str, *reemplazos: tuple[str, str], idempotente: bool = True) -> str:
    """Aplica reemplazos exactos a un archivo.

    - Si `new` ya está presente y `idempotente`, se salta (no reaplica).
    - Exige que `old` aparezca exactamente 1 vez (ancla segura); si no, error.
    """
    src = _read(rel)
    for old, new in reemplazos:
        if idempotente and new in src and old not in src:
            continue
        n = src.count(old)
        if n != 1:
            raise PatchError(
                f"{rel}: ancla encontrada {n} veces (se esperaba 1): {old[:80]!r}"
            )
        src = src.replace(old, new)
    _write(rel, src)
    return rel


def replace_once(rel: str, old: str, new: str) -> str:
    """Reemplazo único con verificación de ancla (helper directo)."""
    return apply(rel, (old, new))
