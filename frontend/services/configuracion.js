/**
 * configuracion.js — Datos del negocio (nombre) para los tickets.
 *
 * Vista SOLO admin (guard.js la protege por ruta). Persiste el nombre del
 * comercio en la BD vía PUT /configuracion y actualiza `window.NEGOCIO_NOMBRE`
 * (la fuente que leen los tickets de POS y cierre de caja) tras guardar, sin
 * necesidad de recargar la página.
 *
 * Depende de api.js (authFetch) y guard.js (protección de ruta + hidratación).
 */
import { api } from './api.js';
import { mostrarAlerta } from './ui.js';

const $ = (id) => document.getElementById(id);

// Valor "guardado" actual (para detectar cambios sin guardar y para revertir).
let nombreGuardado = '';

/** Refresca la vista previa del ticket con el texto del input. */
function actualizarPreview(valor) {
  const pre = $('ticket-preview-negocio');
  if (!pre) return;
  const nombre = (valor || '').trim();
  // Sin nombre configurado, la línea no se imprime (sin espacio residual),
  // igual que en el comprobante real.
  pre.textContent = nombre;
  pre.style.display = nombre ? '' : 'none';
}

/** Indica si hay cambios sin guardar respecto al último valor persistido. */
function hayCambios() {
  return ($('neg-nombre').value || '').trim() !== nombreGuardado;
}

function actualizarBotones() {
  const btnGuardar = $('btn-neg-guardar');
  const btnRevertir = $('btn-neg-revertir');
  const sucio = hayCambios();
  if (btnGuardar) btnGuardar.disabled = !sucio;
  if (btnRevertir) btnRevertir.disabled = !sucio;
}

/** Carga la configuración actual desde el backend y puebla el formulario. */
async function cargar() {
  try {
    const cfg = await api.getConfig();
    nombreGuardado = (cfg && cfg.nombre) || '';
    $('neg-nombre').value = nombreGuardado;
    actualizarPreview(nombreGuardado);
    const meta = $('neg-actualizado');
    if (meta && cfg?.actualizado_en) {
      const fecha = new Date(cfg.actualizado_en).toLocaleString('es-CL');
      meta.textContent = `Última actualización: ${fecha}`;
      meta.classList.remove('hidden');
    }
    actualizarBotones();
  } catch (e) {
    mostrarAlerta(`No se pudo cargar la configuración: ${e.message}`, 'error');
  }
}

/** Persiste el nombre del negocio. */
async function guardar(e) {
  e.preventDefault();
  const nombre = ($('neg-nombre').value || '').trim();
  const errEl = $('neg-error');
  if (errEl) errEl.classList.add('hidden');

  // Validación: el backend exige un nombre no vacío para guardar. Pero la UI
  // permite dejarlo vacío = sin encabezado. Para respetar ambas semánticas,
  // interpretamos "vacío" como "quitar encabezado": si el usuario realmente
  // quiere vaciarlo, se lo advertimos.
  if (!nombre) {
    const ok = window.confirm(
      '¿Querés dejar el nombre del negocio vacío? Los tickets se imprimirán SIN encabezado.'
    );
    if (!ok) return;
    mostrarAlerta('Para dejar los tickets sin encabezado, el nombre no puede guardarse vacío. Contactá soporte.', 'warn');
    return;
  }

  const btn = $('btn-neg-guardar');
  if (btn) { btn.disabled = true; btn.textContent = 'Guardando...'; }
  try {
    const cfg = await api.updateConfig({ nombre });
    nombreGuardado = (cfg && cfg.nombre) || nombre;
    // Actualiza la fuente global para que los tickets reflejen el cambio al
    // instante, sin recargar la página.
    window.NEGOCIO_NOMBRE = nombreGuardado;
    actualizarPreview(nombreGuardado);
    const meta = $('neg-actualizado');
    if (meta) {
      meta.textContent = `Última actualización: ${new Date().toLocaleString('es-CL')}`;
      meta.classList.remove('hidden');
    }
    mostrarAlerta('Nombre del negocio guardado correctamente.', 'ok');
  } catch (err) {
    if (errEl) {
      errEl.textContent = err.message || 'No se pudo guardar.';
      errEl.classList.remove('hidden');
    } else {
      mostrarAlerta(err.message || 'No se pudo guardar.', 'error');
    }
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Guardar'; }
    actualizarBotones();
  }
}

/** Descarta los cambios y restaura el último valor guardado. */
function revertir() {
  $('neg-nombre').value = nombreGuardado;
  actualizarPreview(nombreGuardado);
  const errEl = $('neg-error');
  if (errEl) errEl.classList.add('hidden');
  actualizarBotones();
}

// ---- Inicialización bajo guardia de seguridad ----
async function init() {
  if (window.authGuardReady) {
    try { await window.authGuardReady; } catch (_) { /* el guard redirige si no hay sesión */ }
  }

  const form = $('form-negocio');
  if (form) form.addEventListener('submit', guardar);
  const input = $('neg-nombre');
  if (input) input.addEventListener('input', () => { actualizarPreview(input.value); actualizarBotones(); });
  const btnRevertir = $('btn-neg-revertir');
  if (btnRevertir) btnRevertir.addEventListener('click', revertir);

  await cargar();
}

init();
