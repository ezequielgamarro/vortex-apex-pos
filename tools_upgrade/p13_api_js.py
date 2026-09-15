"""Módulo 2/3/6 — Endpoints nuevos en api.js (frontend).

  * Productos: exportar (blob) e importar (FormData).
  * Ventas: anular venta.
  * Licencia: estado y activación.
Además, interceptor del 402 (licencia vencida) en handleResponse.
"""
from tools_upgrade.patcher import apply

A = "frontend/services/api.js"

# 1) Interceptor 402 ANTES del chequeo 401/403.
apply(
    A,
    (
        "async function handleResponse(response) {\n"
        "  // Token inválido/expirado o permisos insuficientes → cerrar sesión local\n"
        "  if (response.status === 401 || response.status === 403) {",
        "async function handleResponse(response) {\n"
        "  // 402 Payment Required → LICENCIA VENCIDA. NO se cierra sesión (el\n"
        "  // problema es de pago, no de credenciales): se lanza un error tipado\n"
        "  // para que la vista muestre la pantalla de bloqueo/pago.\n"
        "  if (response.status === 402) {\n"
        "    const data = await response.json().catch(() => ({}));\n"
        "    const err = new Error(data.detail || 'Licencia vencida.');\n"
        "    err.status = 402;\n"
        "    err.codigo = data.codigo || 'LICENCIA_VENCIDA';\n"
        "    window.dispatchEvent(new CustomEvent('licencia-vencida', { detail: err }));\n"
        "    throw err;\n"
        "  }\n"
        "\n"
        "  // Token inválido/expirado o permisos insuficientes → cerrar sesión local\n"
        "  if (response.status === 401 || response.status === 403) {",
    ),
)

# 2) Nuevos métodos del objeto api.
apply(
    A,
    (
        "  adjustStock: (id, cantidad) =>\n"
        "    authFetch(`/productos/${id}/stock?cantidad=${cantidad}`, { method: 'PATCH' }),",
        "  adjustStock: (id, cantidad) =>\n"
        "    authFetch(`/productos/${id}/stock?cantidad=${cantidad}`, { method: 'PATCH' }),\n"
        "  // Exporta el catálogo como .xlsx (blob) y dispara la descarga.\n"
        "  exportProductsExcel: async () => {\n"
        "    const token = getToken();\n"
        "    const res = await fetch(`${baseUrl()}/productos/exportar`, {\n"
        "      headers: token ? { Authorization: `Bearer ${token}` } : {},\n"
        "    });\n"
        "    if (res.status === 402) {\n"
        "      window.dispatchEvent(new CustomEvent('licencia-vencida', {}));\n"
        "      throw Object.assign(new Error('Licencia vencida.'), { status: 402 });\n"
        "    }\n"
        "    if (!res.ok) throw new Error(await parseDetail(res));\n"
        "    const blob = await res.blob();\n"
        "    const url = URL.createObjectURL(blob);\n"
        "    const a = document.createElement('a');\n"
        "    a.href = url;\n"
        "    a.download = 'inventario.xlsx';\n"
        "    document.body.appendChild(a);\n"
        "    a.click();\n"
        "    a.remove();\n"
        "    URL.revokeObjectURL(url);\n"
        "  },\n"
        "  // Importa catálogo desde un File .xlsx (multipart/form-data).\n"
        "  importProductsExcel: async (file) => {\n"
        "    const fd = new FormData();\n"
        "    fd.append('archivo', file);\n"
        "    const token = getToken();\n"
        "    const res = await fetch(`${baseUrl()}/productos/importar`, {\n"
        "      method: 'POST',\n"
        "      headers: token ? { Authorization: `Bearer ${token}` } : {},\n"
        "      body: fd,\n"
        "    });\n"
        "    return handleResponse(res);\n"
        "  },",
    ),
)

apply(
    A,
    (
        "  getSale: (id) => authFetch(`/ventas/${id}`),\n"
        "  getSaleDetail: (id) => authFetch(`/ventas/${id}/detalle`),",
        "  getSale: (id) => authFetch(`/ventas/${id}`),\n"
        "  getSaleDetail: (id) => authFetch(`/ventas/${id}/detalle`),\n"
        "  // Anula una venta (solo admin) y revierte stock/cuenta corriente.\n"
        "  voidSale: (id) => authFetch(`/ventas/${id}/anular`, { method: 'POST' }),",
    ),
)

# 3) Métodos de licencia (antes del cierre del objeto api).
apply(
    A,
    (
        "  bestSelling: (since, until, limite = 10) =>\n"
        "    authFetch(`/reportes/mas-vendidos?fecha_desde=${since}&fecha_hasta=${until}&limite=${limite}`),\n"
        "};",
        "  bestSelling: (since, until, limite = 10) =>\n"
        "    authFetch(`/reportes/mas-vendidos?fecha_desde=${since}&fecha_hasta=${until}&limite=${limite}`),\n"
        "\n"
        "  /* ---------- Licencia SaaS ---------- */\n"
        "  licenciaEstado: () => authFetch('/licencia/estado'),\n"
        "  licenciaActivar: (data) =>\n"
        "    authFetch('/licencia/activar', { method: 'POST', body: data }),\n"
        "};",
    ),
)

print("[api.js] OK")
