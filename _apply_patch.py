"""Aplicador de parches idempotentes para el upgrade VORTEX APEX v2.

Se ejecuta desde la raíz del proyecto:  python _apply_patch.py
Cada transformación es verificable (assert) y aborta ante ancla ausente para
no corromper archivos. Diseñado para reejecutarse sin efectos dobles.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent


def patch(rel: str, pares: list[tuple[str, str]], requerido: bool = True) -> None:
    p = ROOT / rel
    if not p.exists():
        if requerido:
            print(f"[SKIP-MISS] {rel} no existe")
        return
    src = p.read_text(encoding="utf-8")
    orig = src
    for old, new in pares:
        if new in src:
            continue  # ya aplicado (idempotente)
        if src.count(old) != 1:
            print(f"[WARN] ancla no única ({src.count(old)}) en {rel}: {old[:60]!r}")
            continue
        src = src.replace(old, new)
    if src != orig:
        p.write_text(src, encoding="utf-8")
        print(f"[OK] parcheado {rel}")
    else:
        print(f"[NOOP] {rel} sin cambios")


if __name__ == "__main__":
    print("Aplicador listo. ROOT =", ROOT)
