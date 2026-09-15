"""Módulo 1 — inventario.js: soporte multi-rubro (talle/color/vencimiento).

  * Lee el rubro del usuario (localStorage.user.rubro) para mostrar/ocultar
    los campos específicos del rubro en el modal de producto.
  * Persiste talle, color y fecha_vencimiento.
"""
from tools_upgrade.patcher import apply

JS = "frontend/services/inventario.js"

# 1) Helper para leer rubro del usuario logueado.
apply(
    JS,
    (
        "/** Determina si la vista es de admin (para activar edición/creación). */\n"
        "function esAdmin() {\n"
        "  try {\n"
        "    const u = JSON.parse(localStorage.getItem('user') || 'null');\n"
        "    return u?.rol === 'admin';\n"
        "  } catch {\n"
        "    return false;\n"
        "  }\n"
        "}",
        "/** Determina si la vista es de admin (para activar edición/creación). */\n"
        "function esAdmin() {\n"
        "  try {\n"
        "    const u = JSON.parse(localStorage.getItem('user') || 'null');\n"
        "    return u?.rol === 'admin';\n"
        "  } catch {\n"
        "    return false;\n"
        "  }\n"
        "}\n"
        "\n"
        "/** Rubro del negocio (multi-rubro). Define qué campos extra se muestran. */\n"
        "function rubroActual() {\n"
        "  try {\n"
        "    const u = JSON.parse(localStorage.getItem('user') || 'null');\n"
        "    return u?.rubro || 'general';\n"
        "  } catch {\n"
        "    return 'general';\n"
        "  }\n"
        "}\n"
        "\n"
        "/**\n"
        " * Muestra u oculta los campos específicos del rubro en el modal.\n"
        " *   - 'indumentaria'       -> talle + color\n"
        " *   - 'panaderia_alimentos'-> fecha de vencimiento\n"
        " * Estructura declarativa: agregar rubro = agregar un caso aquí.\n"
        " */\n"
        "function aplicarRubroUI() {\n"
        "  const rubro = rubroActual();\n"
        "  const showTalle = rubro === 'indumentaria';\n"
        "  const showColor = rubro === 'indumentaria';\n"
        "  const showVenc = rubro === 'panaderia_alimentos';\n"
        "  document.querySelectorAll('[data-rubro=\"talle\"]').forEach((el) => {\n"
        "    el.classList.toggle('hidden', !showTalle);\n"
        "  });\n"
        "  document.querySelectorAll('[data-rubro=\"color\"]').forEach((el) => {\n"
        "    el.classList.toggle('hidden', !showColor);\n"
        "  });\n"
        "  document.querySelectorAll('[data-rubro=\"vencimiento\"]').forEach((el) => {\n"
        "    el.classList.toggle('hidden', !showVenc);\n"
        "  });\n"
        "}",
    ),
)

# 2) abrirModal: poblar los nuevos campos.
apply(
    JS,
    (
        "  $('prod-descripcion').value = prod?.descripcion || '';\n"
        "  $('prod-tipo').value = prod?.tipo_unidad || 'unidad';",
        "  $('prod-descripcion').value = prod?.descripcion || '';\n"
        "  $('prod-tipo').value = prod?.tipo_unidad || 'unidad';\n"
        "  // Campos multi-rubro (existen en el DOM; se ocultan por CSS si no aplican).\n"
        "  const elTalle = $('prod-talle');\n"
        "  if (elTalle) elTalle.value = prod?.talle || '';\n"
        "  const elColor = $('prod-color');\n"
        "  if (elColor) elColor.value = prod?.color || '';\n"
        "  const elVenc = $('prod-vencimiento');\n"
        "  if (elVenc) elVenc.value = prod?.fecha_vencimiento\n"
        "    ? String(prod.fecha_vencimiento).slice(0, 10)\n"
        "    : '';\n"
        "  aplicarRubroUI();",
    ),
)

# 3) guardar(): incluir los nuevos campos en el payload.
apply(
    JS,
    (
        "    descripcion: $('prod-descripcion').value.trim() || null,\n"
        "    activo: $('prod-activo').checked,\n"
        "  };",
        "    descripcion: $('prod-descripcion').value.trim() || null,\n"
        "    activo: $('prod-activo').checked,\n"
        "    talle: $('prod-talle')?.value.trim() || null,\n"
        "    color: $('prod-color')?.value.trim() || null,\n"
        "    fecha_vencimiento: $('prod-vencimiento')?.value\n"
        "      ? `${$('prod-vencimiento').value}T00:00:00`\n"
        "      : null,\n"
        "  };",
    ),
)

# 4) init(): aplicar UI de rubro.
apply(
    JS,
    (
        "  toggleModales();\n"
        "  await cargar();\n"
        "}",
        "  toggleModales();\n"
        "  aplicarRubroUI();\n"
        "  await cargar();\n"
        "}",
    ),
)

print("[inventario.js rubro] OK")
