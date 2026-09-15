"""Router CRUD ligero de Categorías de productos.

Las categorías se guardan en la tabla maestra `categorias` (nombre único) y se
usan opcionalmente en el formulario de productos. Se mantiene la convivencia
con la columna `Producto.categoria` (texto) para no romper vistas existentes:
el formulario de inventario tom óptimamente el nombre de la categoría. Aquí se
depositan las categoría que el usuario crea explícitamente (modal rápido "+"),
y la creación es idempotente (si ya existe por nombre se retorna la existente).
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, requiere_rol, UsuarioActual
from app.models import Categoria
from app.schemas.categoria import CategoriaCreate, CategoriaOut

router = APIRouter(prefix="/categorias", tags=["Categorías"])


@router.get(
    "",
    response_model=List[CategoriaOut],
    summary="Listar categorías",
)
def listar_categorias(
    usuario: UsuarioActual = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Devuelve todas las categorías maestras ordenadas por nombre."""
    try:
        return db.query(Categoria).order_by(Categoria.nombre.asc()).all()
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al listar categorías: {str(exc)}",
        )


@router.post(
    "",
    response_model=CategoriaOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una categoría (idempotente por nombre)",
)
def crear_categoria(
    categoria: CategoriaCreate,
    usuario: UsuarioActual = Depends(requiere_rol("admin")),
    db: Session = Depends(get_db),
):
    """Registra una categoría maestra. Si ya existe una con ese nombre
    (case-insensitive) se retorna la existente en lugar de duplicar."""
    try:
        nombre = categoria.nombre.strip()
        existente = (
            db.query(Categoria)
            .filter(Categoria.nombre.ilike(nombre))
            .first()
        )
        if existente is not None:
            return existente
        nueva = Categoria(nombre=nombre)
        db.add(nueva)
        db.commit()
        db.refresh(nueva)
        return nueva
    except Exception as exc:  # pragma: no cover
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al crear la categoría: {str(exc)}",
        )
