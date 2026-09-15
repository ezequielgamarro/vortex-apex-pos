/**
 * api.js — Capa de red (HTTP client) del Punto de Venta → backend local FastAPI.
 *
 * Cliente `fetch` centralizado que:
 *   - Inyecta automáticamente `Authorization: Bearer <token>` (JWT local) en
 *     todas las peticiones.
 *   - Puntúa {API_BASE_URL} desde window (definido en services/config.js).
 *
 * Mapea 1:1 con los routers del backend (app/main.py): prefijo `/api`.
 * Ya NO depende de Supabase/Mock: trabaja contra el backend real local.
 */

// Clave de almacenamiento del token en localStorage (igual que auth.js/guard.js)
const TOKEN_KEY = 'token';
const USER_KEY = 'user';

// Base de la API. config.js (script clásico) define window.API_BASE_URL.
// Se lee en cada llamada para tolerar script-tag tardío.
function baseUrl() {
  return window.API_BASE_URL || 'http://127.0.0.1:8000/api';
}

// ============================================================
// SESIÓN (JWT local)
// ============================================================
export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem('rol');
}

// ============================================================
// HELPERS DE PETICIÓN
// ============================================================
function buildHeaders(override = {}) {
  const headers = new Headers(override);
  if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const token = getToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  return headers;
}

async function parseDetail(response) {
  try {
    const b = await response.json();
    // FastAPI devuelve el detalle de error en `detail` (string o lista).
    if (typeof b?.detail === 'string') return b.detail;
    if (Array.isArray(b?.detail)) return b.detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
  } catch (_) { /* vacío */ }
  return `Error ${response.status}`;
}

async function handleResponse(response) {
  // 402 Payment Required → LICENCIA VENCIDA. NO se cierra sesión (el
  // problema es de pago, no de credenciales): se lanza un error tipado
  // para que la vista muestre la pantalla de bloqueo/pago.
  if (response.status === 402) {
    const data = await response.json().catch(() => ({}));
    const err = new Error(data.detail || 'Licencia vencida.');
    err.status = 402;
    err.codigo = data.codigo || 'LICENCIA_VENCIDA';
    window.dispatchEvent(new CustomEvent('licencia-vencida', { detail: err }));
    throw err;
  }

  // Token inválido/expirado o permisos insuficientes → cerrar sesión local
  if (response.status === 401 || response.status === 403) {
    clearSession();
    if (typeof window !== 'undefined' &&
        window.location.pathname.indexOf('login.html') === -1) {
      window.location.replace('login.html');
    }
    throw Object.assign(new Error('Sesión caducada. Inicia sesión de nuevo.'), { status: response.status });
  }

  if (!response.ok) {
    const err = new Error(await parseDetail(response));
    err.status = response.status;
    throw err;
  }

  if (response.status === 204) return null;
  const text = await response.text();
  return text ? JSON.parse(text) : null;
}

/**
 * Función helper centralizada de peticiones `fetch` a la API local.
 * Incluye automáticamente Content-Type: application/json y
 * Authorization: Bearer <token> (si existe).
 *
 * @param {string} path    - Ruta relativa bajo /api (p. ej. "/productos")
 * @param {Object} options - { method, body, headers }
 */
export async function authFetch(path, options = {}) {
  const { method = 'GET', body, headers, auth = true } = options;

  const config = { method, headers: buildHeaders(headers) };
  if (!auth) config.headers.delete('Authorization'); // rutas públicas (login)

  if (body !== undefined && body !== null) {
    config.body = typeof body === 'string' ? body : JSON.stringify(body);
  }

  try {
    const response = await fetch(`${baseUrl()}${path}`, config);
    return handleResponse(response);
  } catch (err) {
    // fetch lanza TypeError cuando no hay servidor (backend apagado).
    throw err;
  }
}

/**
 * API tipada, mapeo 1:1 con los routers del backend local.
 */
export const api = {
  /* ---------- Autenticación / Perfil ---------- */
  // login se maneja en auth.js (usa formato urlencoded); perfil vía token:
  getProfile: () => authFetch('/auth/perfil'),
  listUsers: () => authFetch('/auth/usuarios'),
  setUserRole: (userId, rol) =>
    authFetch(`/auth/usuarios/${userId}/rol?rol=${rol}`, { method: 'PATCH' }),
  createUser: (data) => authFetch('/auth/usuarios', { method: 'POST', body: data }),
  setUserActive: (userId, activo) =>
    authFetch(`/auth/usuarios/${userId}/estado?activo=${activo}`, { method: 'PATCH' }),

  /* ---------- Productos ---------- */
  getProducts: (params = '') => authFetch(`/productos${params}`),
  getProduct: (id) => authFetch(`/productos/${id}`),
  getByBarcode: (codigo) => authFetch(`/productos/codigo/${codigo}`),
  lowStock: () => authFetch('/productos/bajo-stock'),
  createProduct: (data) => authFetch('/productos', { method: 'POST', body: data }),
  updateProduct: (id, data) => authFetch(`/productos/${id}`, { method: 'PATCH', body: data }),
  deleteProduct: (id) => authFetch(`/productos/${id}`, { method: 'DELETE' }),
  adjustStock: (id, cantidad) =>
    authFetch(`/productos/${id}/stock?cantidad=${cantidad}`, { method: 'PATCH' }),
  // Exporta el catálogo como .xlsx (blob) y dispara la descarga.
  exportProductsExcel: async () => {
    const token = getToken();
    const res = await fetch(`${baseUrl()}/productos/exportar`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (res.status === 402) {
      window.dispatchEvent(new CustomEvent('licencia-vencida', {}));
      throw Object.assign(new Error('Licencia vencida.'), { status: 402 });
    }
    if (!res.ok) throw new Error(await parseDetail(res));
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'inventario.xlsx';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
  // Importa catálogo desde un File .xlsx (multipart/form-data).
  importProductsExcel: async (file) => {
    const fd = new FormData();
    fd.append('archivo', file);
    const token = getToken();
    const res = await fetch(`${baseUrl()}/productos/importar`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: fd,
    });
    return handleResponse(res);
  },

  /* ---------- Categorías ---------- */
  getCategories: () => authFetch('/categorias'),
  createCategory: (data) => authFetch('/categorias', { method: 'POST', body: data }),

  /* ---------- Configuración del negocio ---------- */
  // Singleton (id=1). Lectura para cualquier usuario; escritura solo admin.
  getConfig: () => authFetch('/configuracion'),
  updateConfig: (data) => authFetch('/configuracion', { method: 'PUT', body: data }),

  /* ---------- Clientes / Cuentas Corrientes ---------- */
  getClients: (soloDeudores = false) =>
    authFetch(`/clientes?solo_deudores=${soloDeudores}`),
  getClient: (id) => authFetch(`/clientes/${id}`),
  createClient: (data) => authFetch('/clientes', { method: 'POST', body: data }),
  registerAbono: (clienteId, data) =>
    authFetch(`/clientes/${clienteId}/abonos`, { method: 'POST', body: data }),
  listCuentaMovimientos: (clienteId) =>
    authFetch(`/movimientos${clienteId ? `?cliente_id=${clienteId}` : ''}`),

  /* ---------- Ventas ---------- */
  registerSale: (data) => authFetch('/ventas', { method: 'POST', body: data }),
  listSales: (params = '') => authFetch(`/ventas${params}`),
  listSalesDetailed: (limite = 200) => authFetch(`/ventas/historial-detallado?limite=${limite}`),
  getSale: (id) => authFetch(`/ventas/${id}`),
  getSaleDetail: (id) => authFetch(`/ventas/${id}/detalle`),
  // Anula una venta (solo admin) y revierte stock/cuenta corriente.
  voidSale: (id, data) => authFetch(`/ventas/${id}/anular`, { method: 'POST', body: data }),

  /* ---------- Arqueo / Caja ---------- */
  openCash: (data) => authFetch('/arqueo/abrir', { method: 'POST', body: data }),
  closeCash: (data) => authFetch('/arqueo/cerrar', { method: 'POST', body: data }),
  addMovement: (data) => authFetch('/arqueo/movimiento', { method: 'POST', body: data }),
  activeCash: () => authFetch('/arqueo/activo'),
  cashSummary: () => authFetch('/arqueo/resumen'),
  cashHistory: (limite = 50) => authFetch(`/arqueo/historial?limite=${limite}`),
  // Resumen exhaustivo de un arqueo por su ID (activo o cerrado). Alimenta el
  // ticket de cierre imprimible del Historial de Cajas.
  cashResumenArqueo: (arqueoId) => authFetch(`/arqueo/${arqueoId}/resumen`),

  /* ---------- Reportes / Dashboard ---------- */
  // Dashboard analítico (solo admin): series, top productos y métodos de pago.
  // `agrupacion` = 'dias' | 'meses'; `rango` = nº de periodos (0 = default).
  dashboardAnalytics: (agrupacion = 'dias', rango = 0) =>
    authFetch(`/reportes/dashboard?agrupacion=${agrupacion}&rango=${rango}`),
  dashboard: () => authFetch('/reportes/dashboard'),
  salesReport: (since, until) =>
    authFetch(`/reportes/ventas?fecha_desde=${since}&fecha_hasta=${until}`),
  bestSelling: (since, until, limite = 10) =>
    authFetch(`/reportes/mas-vendidos?fecha_desde=${since}&fecha_hasta=${until}&limite=${limite}`),

  /* ---------- Licencia SaaS ---------- */
  licenciaEstado: () => authFetch('/licencia/estado'),
  licenciaActivar: (data) =>
    authFetch('/licencia/activar', { method: 'POST', body: data }),
};

export default api;
