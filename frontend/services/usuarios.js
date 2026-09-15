/**
 * usuarios.js — Administración de usuarios (solo rol admin).
 *
 * Para llegar aquí el `guard.js` exige rol === 'admin'. Este módulo:
 *   - lista los usuarios del sistema,
 *   - crea usuarios nuevos asignando rol (admin/cajero),
 *   - cambia el rol de un usuario,
 *   - activa/desactiva una cuenta.
 *
 * MODELO DE PERMISOS (SuperAdministrador):
 *   - El SuperAdministrador (cuenta semilla, p.ej. `admin@pos.local`) es la
 *     ÚNICA autoridad que puede ELEGIR el `rubro` de un usuario. La bandera
 *     autoritativa la entrega el backend en `/auth/perfil` (`es_superadmin`);
 *     el frontend NO hardcodea el email (Single Source of Truth en backend).
 *   - Un administrador estándar NO ve el selector de rubro; el backend, además,
 *     IGNORA cualquier `rubro` enviado por él y hereda el del comercio.
 *   - La cuenta del SuperAdmin está OCULTA para los administradores estándar
 *     (el backend ya la excluye del listado); solo él la ve.
 *
 * Se apoya en los endpoints del backend (app/routers/auth.py):
 *   GET    /auth/usuarios
 *   POST   /auth/usuarios            (crear con rol; rubro solo SuperAdmin)
 *   PATCH  /auth/usuarios/{id}/rol?rol=...
 *   PATCH  /auth/usuarios/{id}/estado?activo=...
 */
import { api } from './api.js';
import { mostrarAlerta } from './ui.js';

const $ = (id) => document.getElementById(id);

let usuarios = [];
let miRol = 'cajero';
// Bandera AUTORITATIVA del backend: ¿el usuario activo es el SuperAdmin?
let esSuperAdmin = false;

/** Perfil actual (id/rol) leído de localStorage para la UI. */
function perfilLocal() {
  try {
    return JSON.parse(localStorage.getItem('user') || 'null') || {};
  } catch {
    return {};
  }
}

function render() {
  const tbody = $('tabla-usuarios');
    tbody.innerHTML = '';

  const yo = perfilLocal();

  if (!usuarios.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="text-center text-pos-text-body/60 py-8">Todavía no hay usuarios registrados.</td></tr>';
    return;
  }

  usuarios.forEach((u) => {
    const esYo = String(u.id) === String(yo.id);
    // El SuperAdmin (u.es_superadmin) queda BLINDADO para admins estándar:
    // no se puede cambiar su rol ni su estado. El backend también lo impone.
    const objetivoEsSuper = !!u.es_superadmin;
    const bloquearAcciones = objetivoEsSuper && !esSuperAdmin;

    const rolCell = bloquearAcciones
      ? '<span class="badge badge-primary">SuperAdmin</span>'
      : `<select class="form-input-pos !px-2 !py-1 text-sm rol-select" data-id="${u.id}">
           <option value="cajero" ${u.rol === 'cajero' ? 'selected' : ''}>Cajero</option>
           <option value="admin" ${u.rol === 'admin' ? 'selected' : ''}>Admin</option>
         </select>`;

    const accionesCell = esYo
      ? '<span class="text-xs text-pos-text-body/60 font-medium inline-flex items-center">No podés cambiarte roles ni desactivarte</span>'
      : bloquearAcciones
        ? '<span class="text-xs text-pos-text-body/60 font-medium inline-flex items-center">Cuenta protegida</span>'
        : `<button data-toggle="${u.id}" data-activo="${u.activo ? 'true' : 'false'}" class="btn-secondary !px-3 !py-1.5 text-xs">
             ${u.activo ? 'Desactivar' : 'Activar'}
           </button>`;

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>
        <div class="font-medium ${esYo ? 'text-pos-primary' : ''}">${u.nombre_completo || u.nombre || '—'} ${esYo ? '<span class="badge badge-primary ml-1">vos</span>' : ''}</div>
      </td>
      <td class="text-sm">${u.email || '—'}</td>
      <td>${rolCell}</td>
      <td>
        <span class="badge ${u.activo ? 'badge-primary' : 'badge-neutral'}">${u.activo ? 'Activo' : 'Inactivo'}</span>
      </td>
      <td>
        <div class="flex justify-end gap-2">${accionesCell}</div>
      </td>`;
    tbody.appendChild(tr);
  });

  // Cambio de rol en el <select>.
  tbody.querySelectorAll('.rol-select').forEach((sel) => {
    sel.addEventListener('change', async () => {
      const id = sel.dataset.id;
      const rol = sel.value;
      try {
        await api.setUserRole(id, rol);
        await cargar();
      } catch (err) {
        mostrarAlerta(`No se pudo cambiar el rol: ${err.message}`, 'error');
        await cargar(); // re-renderiza para recuperar el valor previo
      }
    });
  });

  // Activar / desactivar.
  tbody.querySelectorAll('[data-toggle]').forEach((b) => {
    b.addEventListener('click', async () => {
      const id = b.dataset.id;
      const act = b.dataset.activo === 'true';
      const nuevo = !act;
      if (nuevo === false && !window.confirm('¿Desactivar este usuario? No podrá iniciar sesión hasta que lo actives de nuevo.')) return;
      try {
        await api.setUserActive(id, nuevo);
        await cargar();
      } catch (err) {
        mostrarAlerta(`No se pudo actualizar el estado: ${err.message}`, 'error');
        await cargar();
      }
    });
  });
}

async function cargar() {
  try {
    // El backend ya excluye la cuenta del SuperAdmin para admins estándar; el
    // frontend NO filtra por email (evita duplicar la regla de negocio).
    usuarios = (await api.listUsers()) || [];
    render();
  } catch (e) {
    $('tabla-usuarios').innerHTML =
      `<tr><td colspan="5" class="text-center text-pos-danger py-8">No se pudieron cargar los usuarios: ${e.message}</td></tr>`;
  }
}

function cerrarModal() {
  const m = $('modal-usuario');
  if (!m) return;
  m.classList.add('hidden');
  m.classList.remove('flex');
  $('u-error').classList.add('hidden');
}

/**
 * Muestra u oculta el bloque "Rubro" del modal según el perfil activo.
 * Función dedicada (no lógica dispersa) para que la regla "solo el SuperAdmin
 * elige rubro" viva en un ÚNICO lugar del frontend.
 */
function aplicarVisibilidadRubro() {
  const bloque = $('bloque-rubro');
  if (!bloque) return;
  bloque.classList.toggle('hidden', !esSuperAdmin);
}

function abrirModal() {
  // Resetea el formulario (incluido el rubro, si el campo aplica).
  ['u-nombre', 'u-email', 'u-password'].forEach((id) => { if ($(id)) $(id).value = ''; });
  const rubroSel = $('u-rubro');
  if (rubroSel) rubroSel.value = 'general';
  aplicarVisibilidadRubro();
  $('u-error').classList.add('hidden');
  $('modal-usuario').classList.remove('hidden');
  $('modal-usuario').classList.add('flex');
  $('u-nombre').focus();
}

async function crear(e) {
  e.preventDefault();
  const nombre = $('u-nombre').value.trim();
  const email = $('u-email').value.trim();
  const password = $('u-password').value;
  const rol = $('u-rol').value;

  const errEl = $('u-error');
  if (errEl) errEl.classList.add('hidden');
  if (!nombre) return mostrarError('Ingresá el nombre.');
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return mostrarError('Ingresá un correo válido.');
  if (password.length < 6) return mostrarError('La contraseña debe tener al menos 6 caracteres.');

  const btn = e.target.querySelector('button[type="submit"]');
  if (btn) { btn.disabled = true; btn.textContent = 'Creando...'; }
  try {
    const payload = { nombre, email, password, rol };
    // El rubro SOLO lo envía el SuperAdmin. Para un admin estándar se omite por
    // completo: el backend hereda el del comercio. (Defensa en profundidad: el
    // backend igualmente ignora cualquier rubro de un no-SuperAdmin.)
    if (esSuperAdmin) {
      const rubroSel = $('u-rubro');
      if (rubroSel) payload.rubro = rubroSel.value;
    }
    await api.createUser(payload);
    cerrarModal();
    await cargar();
  } catch (err) {
    mostrarError(err.message || 'No se pudo crear el usuario.');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Crear usuario'; }
  }
}

function mostrarError(msg) {
  const el = $('u-error');
  if (!el) return mostrarAlerta(msg, 'error');
  el.textContent = msg;
  el.classList.remove('hidden');
}

// ---- Inicialización bajo guardia de seguridad ----
async function init() {
  let perfilResuelto = null;
  try { perfilResuelto = window.authGuardReady && await window.authGuardReady; }
  catch (_) { /* el guard redirigió si no había sesión */ }

  // Solo un rol admin debe operar este módulo (el guard.js ya redirige si no).
  miRol = perfilResuelto?.rol || perfilLocal().rol || 'cajero';

  // Determinar si el usuario activo es el SuperAdmin. Preferimos el dato del
  // backend (`es_superadmin` en /auth/perfil); si no viniera, se consulta.
  if (perfilResuelto && typeof perfilResuelto.es_superadmin === 'boolean') {
    esSuperAdmin = perfilResuelto.es_superadmin;
  } else {
    try {
      const p = await api.getProfile();
      esSuperAdmin = !!p?.es_superadmin;
    } catch (_) {
      esSuperAdmin = false;
    }
  }
  aplicarVisibilidadRubro();

  const btn = $('btn-nuevo');
  if (btn) btn.addEventListener('click', abrirModal);
  const form = $('form-usuario');
  if (form) form.addEventListener('submit', crear);

  await cargar();
}

init();