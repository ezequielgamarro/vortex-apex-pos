/**
 * ventas.js — Historial de Ventas agrupado por fecha.
 *
 * Consume el endpoint consolidado `GET /api/ventas/historial-detallado`, que
 * devuelve cada venta (ordenada de más reciente a más antigua) con el detalle
 * de sus productos. Este módulo agrupa los tickets por día y los presenta en
 * tarjetas `<details>/<summary>` (acordeón nativo, sin dependencias).
 *
 * Módulo 3 (Anulación segura): el admin puede anular una venta (revierte stock
 * y cuenta corriente en el backend). Las ventas anuladas se muestran con un
 * badge y sin botón de anular.
 *
 * Depende de api.js (authFetch) y guard.js (protección de la ruta).
 */
import { api } from './api.js';
import { mostrarAlerta } from './ui.js';

const $ = (id) => document.getElementById(id);

const money = (n) =>
  new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP' }).format(n || 0);

/** Formatea una fecha ISO a DD/MM/AAAA en hora local. */
function fechaLocal(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString('es-CL', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

/** Formatea una hora (hh:mm) en hora local. */
function horaLocal(iso) {
  const d = new Date(iso);
  return d.toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' });
}

const METODO_LABEL = {
  efectivo: 'Efectivo',
  tarjeta: 'Tarjeta',
  transferencia: 'Transferencia',
  mixto: 'Mixto',
  cuenta_corriente: 'Cuenta Corriente',
};

/** Etiqueta legible de un método de pago. */
function metodoLabel(m) {
  return METODO_LABEL[m] || (m || '—');
}

/** Escapa HTML para evitar inyección (nombres de cliente/producto). */
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

/** Determina si el usuario actual es admin (para habilitar la anulación). */
function esAdmin() {
  return localStorage.getItem('rol') === 'admin';
}

/** Guarda el ID de la venta que se está por anular (la acción pide confirmación). */
let idAnular = null;

/**
 * Construye el HTML de un solo ticket (desplegable anidado).
 */
function ticketHTML(v) {
  const items = v.items || [];
  const anulada = String(v.estado || '').toLowerCase() === 'anulada';
  const filas = items.map((it) => `
      <tr>
        <td class="py-1.5 pr-3 text-pos-text-body">${esc(it.nombre_producto)}</td>
        <td class="py-1.5 px-2 text-right whitespace-nowrap text-pos-text-body/80">${Number(it.cantidad || 0).toLocaleString('es-CL')}</td>
        <td class="py-1.5 px-2 text-right whitespace-nowrap text-pos-text-body">${money(it.precio_unitario)}</td>
        <td class="py-1.5 pl-2 text-right whitespace-nowrap font-medium text-pos-text-head">${money(it.subtotal)}</td>
      </tr>`).join('');

  // Botón de anular: SOLO admin y SOLO si la venta está activa.
  const botonAnular = (esAdmin() && !anulada)
    ? `<button type="button" data-anular="${v.id}" data-folio="${esc(v.folio)}" class="btn-danger !px-3 !py-1.5 text-xs">Anular</button>`
    : '';

  return `
    <article class="pos-card p-4 ${anulada ? 'opacity-70' : ''}">
      <!-- Cabecera del ticket -->
      <div class="flex flex-wrap items-center gap-x-4 gap-y-1">
        <span class="font-mono text-sm font-semibold text-pos-primary">${esc(v.folio)}</span>
        <span class="text-sm text-pos-text-body/70">${horaLocal(v.fecha)} h</span>
        <span class="badge badge-neutral">${metodoLabel(v.metodo_pago)}</span>
        ${anulada ? '<span class="badge badge-danger">Anulada</span>' : ''}
        <span class="text-sm text-pos-text-body/80 ml-auto">${esc(v.cliente || 'Mostrador')}</span>
        <span class="text-base font-bold text-pos-text-head ${anulada ? 'line-through' : ''}">${money(v.total)}</span>
        ${botonAnular}
      </div>

      ${anulada && v.anulada_por ? `<p class="text-xs text-pos-text-body/60 mt-1">Anulada por ${esc(v.anulada_por)}${v.anulada_en ? ` el ${fechaLocal(v.anulada_en)}` : ''}.</p>` : ''}

      <!-- Detalle de productos (colapsado por defecto) -->
      ${items.length ? `
        <details class="mt-3 border-t border-pos-secondary/30 pt-2">
          <summary class="cursor-pointer text-sm text-pos-primary hover:underline select-none">Detalle de productos</summary>
          <div class="mt-2 overflow-x-auto">
            <table class="min-w-full text-sm">
              <thead>
                <tr class="text-xs text-pos-text-body/60 uppercase tracking-wide">
                  <th class="text-left pb-1 font-semibold">Producto</th>
                  <th class="text-right pb-1 font-semibold">Cant.</th>
                  <th class="text-right pb-1 font-semibold">P. unit.</th>
                  <th class="text-right pb-1 font-semibold">Subtotal</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-pos-secondary/20">${filas}</tbody>
            </table>
          </div>
        </details>` : ''}
    </article>`;
}

/**
 * Construye el acordeón agrupado por fecha.
 * @param {Array} ventas  Lista de ventas (nombres/índices según API).
 */
function renderPorFecha(ventas) {
  const cont = $('historial-por-fecha');
  cont.innerHTML = '';

  // Agrupar por clave de fecha local (YYYYMMDD) manteniéndolas en orden de aparición.
  const grupos = new Map();
  for (const v of ventas) {
    const d = new Date(v.fecha);
    const clave = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    if (!grupos.has(clave)) grupos.set(clave, []);
    grupos.get(clave).push(v);
  }

  // Ordenar fechas descendente (más reciente primero).
  const claves = [...grupos.keys()].sort((a, b) => (a < b ? 1 : -1));

  if (!claves.length) {
    $('historial-vacio').classList.remove('hidden');
    $('resumen-total').classList.add('hidden');
    return;
  }
  $('historial-vacio').classList.add('hidden');

  // Total global de lo mostrado (solo ventas NO anuladas).
  let global = 0;

  for (const clave of claves) {
    const tickets = grupos.get(clave);
    const totalDia = tickets.reduce((acc, v) => {
      const anulada = String(v.estado || '').toLowerCase() === 'anulada';
      return acc + (anulada ? 0 : (Number(v.total) || 0));
    }, 0);
    global += totalDia;

    const fechaISO = new Date(clave + 'T12:00:00');
    const etiquetaFecha = fechaLocal(fechaISO.toISOString());
    const tasa = tickets.length === 1 ? '1 venta' : `${tickets.length} ventas`;

    const detalle = document.createElement('details');
    detalle.className = 'pos-card overflow-hidden';
    detalle.innerHTML = `
      <summary class="flex items-center justify-between gap-3 p-4 cursor-pointer select-none hover:bg-pos-secondary/30 transition-colors" style="list-style:none;">
        <div class="flex items-center gap-3">
          <svg class="h-5 w-5 text-pos-primary flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
          <div>
            <p class="font-semibold text-pos-text-head text-sm sm:text-base">Fecha: ${etiquetaFecha}</p>
            <p class="text-xs text-pos-text-body/60">${tasa}</p>
          </div>
        </div>
        <div class="flex items-center gap-2 text-right">
          <span class="text-base font-bold text-pos-primary">${money(totalDia)}</span>
          <svg class="h-5 w-5 text-pos-text-body/40 flex-shrink-0 chevron" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
        </div>
      </summary>
      <div class="px-4 pb-4 space-y-3 border-t border-pos-secondary/30 pt-3">
        ${tickets.map(ticketHTML).join('')}
      </div>`;

    cont.appendChild(detalle);
  }

  // Enlazar botones de anular (delegación tras render).
  cont.querySelectorAll('[data-anular]').forEach((b) => {
    b.addEventListener('click', () => abrirModalAnular(b.dataset.anular, b.dataset.folio));
  });

  $('resumen-total').classList.remove('hidden');
  $('resumen-total-monto').textContent = money(global);
}

// ---- Módulo 3: modal de anulación ----
function abrirModalAnular(id, folio) {
  idAnular = id;
  const f = $('anular-folio');
  if (f) f.textContent = folio || '';
  const m = $('modal-anular');
  if (m) { m.classList.remove('hidden'); m.classList.add('flex'); }
}

function cerrarModalAnular() {
  idAnular = null;
  const m = $('modal-anular');
  if (m) { m.classList.add('hidden'); m.classList.remove('flex'); }
  const inp = $('anular-motivo');
  if (inp) inp.value = '';
}

async function confirmarAnular() {
  if (!idAnular) return;
  const motivo = ($('anular-motivo')?.value || '').trim();
  const password = ($('anular-password')?.value || '').trim();
  
  if (!motivo) {
    mostrarAlerta('Debes ingresar un motivo para la anulación.', 'error');
    return;
  }
  if (!password) {
    mostrarAlerta('Debes ingresar tu contraseña de admin.', 'error');
    return;
  }

  const btn = $('btn-confirmar-anular');
  if (btn) { btn.disabled = true; btn.textContent = 'Anulando…'; }
  try {
    await api.voidSale(idAnular, { motivo, password });
    cerrarModalAnular();
    mostrarAlerta('Venta anulada. El stock fue repuesto.', 'ok');
    await cargar();
  } catch (err) {
    mostrarAlerta(`No se pudo anular: ${err.message}`, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Confirmar anulación'; }
  }
}

/** Carga las ventas desde el backend. */
async function cargar() {
  const estado = $('historial-cargando');
  const error = $('historial-error');
  estado.classList.remove('hidden');
  estado.textContent = 'Cargando ventas…';
  error.classList.add('hidden');
  $('btn-refrescar').disabled = true;

  try {
    const ventas = await api.listSalesDetailed(500);
    renderPorFecha(ventas || []);
    estado.classList.add('hidden');
  } catch (e) {
    estado.classList.add('hidden');
    error.textContent = `No se pudo cargar el historial: ${e.message}`;
    error.classList.remove('hidden');
  } finally {
    $('btn-refrescar').disabled = false;
  }
}

// ---- Inicialización bajo guardia de seguridad ----
async function init() {
  if (window.authGuardReady) await window.authGuardReady;

  $('btn-refrescar').addEventListener('click', cargar);
  $('btn-confirmar-anular')?.addEventListener('click', confirmarAnular);
  $('btn-cancelar-anular')?.addEventListener('click', cerrarModalAnular);
  await cargar();
}

init();