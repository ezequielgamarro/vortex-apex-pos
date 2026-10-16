/**
 * historial-cajas.js — Historial de Cajas cerradas + ticket de cierre imprimible.
 *
 * Flujo:
 *   1) Puebla el DataGrid con `api.cashHistory()`  -> GET /api/arqueo/historial
 *      (lista de arqueos con estado "cerrado", ordenados por fecha_cierre desc).
 *   2) En la columna "Acciones" inyecta un botón "🖨️ Imprimir" por fila.
 *   3) Al hacer clic, `imprimirResumenCaja(id)` consulta
 *      `api.cashResumenArqueo(id)`  -> GET /api/arqueo/{arqueo_id}/resumen,
 *      construye el HTML del ticket de cierre en el contenedor oculto
 *      `#area-impresion` y dispara `window.print()`.
 *
 * La impresión usa el patrón clásico de visibilidad: en pantalla el contenedor
 * está vacío/oculto; al imprimir, la regla `@media print` oculta todo el sistema
 * (aside, header, main, scripts) y muestra únicamente el ticket con ancho típico
 * de impresora térmica (~80mm). Requisito: no depender del layout de pantalla.
 *
 * Depende de api.js (authFetch) y guard.js (protección de ruta).
 */
import { api } from './api.js';
import { mostrarAlerta } from './ui.js';

const $ = (id) => document.getElementById(id);

/** Formatea un importe como moneda chilena (CLP). */
const money = (n) =>
  new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP' }).format(n || 0);

/** Formatea un ISO datetime a fecha local DD/MM/AAAA HH:MM. */
function fechaHora(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString('es-CL', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

/** Escapa HTML para evitar inyección de datos no confiables. */
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

/** Trunca un UUID para mostrarlo compacto como ID de turno. */
function idCorto(uuid) {
  return String(uuid || '').slice(0, 8);
}

/** Signo/color semántico de la diferencia (cuadre, sobrante o faltante). */
function badgeDiferencia(diff) {
  const n = Number(diff || 0);
  if (Math.abs(n) < 0.005) {
    return '<span class="badge badge-neutral">Cuadre</span>';
  }
  if (n > 0) return `<span class="badge badge-primary">+ ${money(n)}</span>`;
  return `<span class="badge badge-danger">- ${money(Math.abs(n))}</span>`;
}

/**
 * Puebla la tabla con las cajas cerradas del historial.
 * @param {Array} arqueos  Respuesta de GET /arqueo/historial (ArqueoOut[]).
 */
function renderHistorial(arqueos) {
  const tbody = $('historial-tabla');
  tbody.innerHTML = '';

  if (!arqueos || !arqueos.length) {
    $('historial-vacio').classList.remove('hidden');
    $('historial-vacio').classList.add('block');
    return;
  }
  $('historial-vacio').classList.add('hidden');
  $('historial-vacio').classList.remove('block');

  for (const a of arqueos) {
    const tr = document.createElement('tr');

    const montoEsperado = money(a.monto_esperado);
    const montoReal = a.monto_real != null ? money(a.monto_real) : '—';
    // Diferencia en la columna dedicada + etiqueta de cuadre.
    const diffCell = (a.diferencia != null) ? badgeDiferencia(a.diferencia) : '—';

    // Fecha de cierre como clave ISO (YYYY-MM-DD) para el filtro por <input date>.
    // Se guarda aparte del texto mostrado (dd/mm/aaaa) → fuente de verdad del filtro.
    tr.dataset.fechaCierre = claveFechaISO(a.fecha_cierre);

    tr.innerHTML = `
      <td class="font-mono text-pos-primary">${esc(idCorto(a.id))}</td>
      <td>${fechaHora(a.fecha_apertura)}</td>
      <td>${fechaHora(a.fecha_cierre)}</td>
      <td class="text-right whitespace-nowrap font-medium">${montoEsperado}</td>
      <td class="text-right whitespace-nowrap">${montoReal}</td>
      <td class="text-right whitespace-nowrap">${diffCell}</td>
      <td class="text-center whitespace-nowrap">
        <button
          type="button"
          class="btn-primary !py-1 !px-3 text-xs gap-1.5"
          data-imprimir="${esc(a.id)}">
          <svg class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4H7v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"/></svg>
          <span>Imprimir</span>
        </button>
      </td>`;

    // Listener en vez de `onclick` inline: la CSP no permite handlers inline.
    tr.querySelector('[data-imprimir]')?.addEventListener('click', (e) =>
      imprimirResumenCaja(e.currentTarget.dataset.imprimir)
    );

    tbody.appendChild(tr);
  }

  // Re-aplicar filtro vigente tras (re)render.
  filtrarHistorial();
}

/**
 * Devuelve la fecha local en formato ISO corto (YYYY-MM-DD) para comparar
 * contra el valor de un <input type="date"> (que usa ese mismo formato).
 * Se calcula en hora local para no desplazar el día por la zona horaria.
 */
function claveFechaISO(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d)) return '';
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/**
 * Filtro client-side por fecha de cierre (client-side, sin ir al backend).
 * Muestra solo las filas cuya fecha de cierre coincida con la elegida.
 */
function filtrarHistorial() {
  const input = $('filtro-fecha');
  const limpiar = $('btn-limpiar-fecha');
  if (!input) return;
  const fecha = input.value || '';
  if (limpiar) limpiar.classList.toggle('hidden', !fecha);

  const tbody = $('historial-tabla');
  const filas = tbody.querySelectorAll('tr[data-fecha-cierre]');
  let visibles = 0;
  filas.forEach((tr) => {
    const coincide = !fecha || tr.dataset.fechaCierre === fecha;
    tr.style.display = coincide ? '' : 'none';
    if (coincide) visibles += 1;
  });

  // Aviso de "sin coincidencias" solo cuando hay historial pero el filtro vacía.
  let aviso = tbody.querySelector('[data-sin-resultados]');
  const debeMostrar = filas.length > 0 && visibles === 0 && !!fecha;
  if (debeMostrar && !aviso) {
    const tr = document.createElement('tr');
    tr.dataset.sinResultados = '1';
    tr.innerHTML = `<td colspan="7" class="text-center text-pos-text-body/70 py-8">Sin cajas cerradas en esa fecha.</td>`;
    tbody.appendChild(tr);
  } else if (!debeMostrar && aviso) {
    aviso.remove();
  }
}

/**
 * Construye dinámicamente el HTML de un ticket de cierre para imprimir.
 * @param {Object} r  Respuesta de GET /arqueo/{id}/resumen.
 */
function construirTicket(r) {
  const caja = (r && r.caja) || {};
  const movs = (r && r.movimientos) || [];

  // Ventas por otros medios (informativas, no ingresan físicamente a la gaveta).
  const notasMedios =
    (Number(r.ventas_tarjeta) || 0) +
    (Number(r.ventas_transferencia) || 0) +
    (Number(r.ventas_mixto) || 0);

  // Desglose de movimientos manuales del turno.
  const filasMov = movs.length
    ? movs.map((m) => `
        <tr>
          <td class="t-izq">${esc(m.concepto || (m.tipo === 'ingreso' ? 'Ingreso' : 'Egreso'))}</td>
          <td class="t-der">${m.tipo === 'ingreso' ? '+' : '-'}${money(m.monto)}</td>
        </tr>`).join('')
    : '<tr><td class="t-izq t-muted" colspan="2">Sin movimientos manuales</td></tr>';

  // Etiqueta de diferencia legible. En el resumen histórico, totales y caja
  // vienen anidados: diferencia/monto_real se leen de `caja.*` (el backend los
  // persiste al cerrar el arqueo); el resto de conceptos vive en la raíz.
  const montoRealPersistido = caja.monto_real != null ? Number(caja.monto_real) : null;
  const totalEsperado = Number(r.total_esperado) || 0;
  const diferenciaPersistida =
    caja.diferencia != null ? Number(caja.diferencia) : null;

  let diffTxt;
  const diff = diferenciaPersistida != null
    ? diferenciaPersistida
    : ((montoRealPersistido != null ? montoRealPersistido : totalEsperado) - totalEsperado);
  if (Math.abs(diff) < 0.005) diffTxt = 'CUADRE EXACTO';
  else if (diff > 0) diffTxt = `SOBRANTE ${money(diff)}`;
  else diffTxt = `FALTANTE ${money(Math.abs(diff))}`;

  // Encabezado del negocio: solo se imprime si hay un nombre configurado.
  // Antes se hardcodeaba 'VORTEX APEX' como fallback, lo que hacía aparecer la
  // marca del software en la factura del comercio. Ahora, sin nombre
  // configurado, la línea no se renderiza (sin espacio en blanco residual).
  const negocioNombre = (window.NEGOCIO_NOMBRE || '').trim();
  const lineaNegocio = negocioNombre
    ? `<div class="t-info t-neg">Negocio:: ${esc(negocioNombre)}</div>`
    : '';

  return `
    <div class="ticket">
      <div class="t-center t-neg">TICKET DE CIERRE DE CAJA</div>
      <div class="t-sep">${'='.repeat(32)}</div>
      ${lineaNegocio}
      <table class="tb-detalle">
        <tr><td class="t-izq">Turno ID</td><td class="t-der">${esc(idCorto(caja.id || r.id))}</td></tr>
        <tr><td class="t-izq">Apertura</td><td class="t-der">${fechaHora(caja.fecha_apertura || r.fecha_apertura)}</td></tr>
        <tr><td class="t-izq">Cierre</td><td class="t-der">${fechaHora(caja.fecha_cierre || r.fecha_cierre)}</td></tr>
      </table>
      <div class="t-sep">${'-'.repeat(32)}</div>
      <table class="tb-detalle">
        <tr><td class="t-izq">Fondo inicial</td><td class="t-der">${money(r.monto_inicial)}</td></tr>
        <tr><td class="t-izq">Ventas en efectivo</td><td class="t-der">${money(r.ventas_efectivo)}</td></tr>
        <tr><td class="t-izq">Ingresos manuales</td><td class="t-der">+${money(r.ingresos_manuales)}</td></tr>
        <tr><td class="t-izq">Egresos manuales</td><td class="t-der">-${money(r.egresos_manuales)}</td></tr>
      </table>
      <div class="t-sep">${'-'.repeat(32)}</div>
      <table class="tb-total">
        <tr>
          <td class="t-izq t-neg"><strong>TOTAL ESPERADO</strong></td>
          <td class="t-der t-neg"><strong>${money(r.total_esperado)}</strong></td>
        </tr>
        <tr>
          <td class="t-izq">Efectivo real contado</td>
          <td class="t-der">${money(montoRealPersistido != null ? montoRealPersistido : totalEsperado)}</td>
        </tr>
        <tr>
          <td class="t-izq t-neg">Diferencia</td>
          <td class="t-der t-neg"><em>${esc(diffTxt)}</em></td>
        </tr>
      </table>
      <div class="t-sep">${'-'.repeat(32)}</div>
      <div class="t-label t-neg">Ventas por otros medios (informativas)</div>
      <table class="tb-detalle">
        <tr><td class="t-izq">Tarjeta</td><td class="t-der">${money(r.ventas_tarjeta)}</td></tr>
        <tr><td class="t-izq">Transferencia</td><td class="t-der">${money(r.ventas_transferencia)}</td></tr>
        <tr><td class="t-izq">Mixto</td><td class="t-der">${money(r.ventas_mixto)}</td></tr>
        <tr><td class="t-izq">Cuenta Corriente</td><td class="t-der">${money(r.ventas_credito)}</td></tr>
        ${
          notasMedios > 0
            ? `<tr><td class="t-izq t-muted">Total otros medios</td><td class="t-der t-muted">${money(notasMedios)}</td></tr>`
            : ''
        }
      </table>
      <div class="t-sep">${'-'.repeat(32)}</div>
      <div class="t-label t-neg">Movimientos manuales</div>
      <table class="tb-detalle">${filasMov}</table>
      ${caja.observaciones_cierre ? `<div class="t-obs"><span class="t-label">Obs. cierre:</span> ${esc(caja.observaciones_cierre)}</div>` : ''}
      ${caja.observaciones_apertura ? `<div class="t-obs"><span class="t-label">Obs. apertura:</span> ${esc(caja.observaciones_apertura)}</div>` : ''}
      <div class="t-sep">${'='.repeat(32)}</div>
      <div class="t-center t-neg">Fin del reporte · ${new Date().toLocaleDateString('es-CL')}</div>
    </div>`;
}

/**
 * Carga y rellena el ticket de una caja, y dispara la impresión nativa.
 * @param {string} arqueoId  UUID del arqueo a imprimir.
 */
async function imprimirResumenCaja(arqueoId) {
  try {
    const resumen = await api.cashResumenArqueo(arqueoId);
    const area = $('area-impresion');
    if (!area) {
      mostrarAlerta('No se encontró la zona de impresión (#area-impresion).', 'error');
      return;
    }
    area.innerHTML = construirTicket(resumen);
    // Imprime lo renderizado (regla @media print muestra sólo el ticket).
    window.print();
  } catch (e) {
    mostrarAlerta(`No se pudo obtener el resumen para imprimir: ${e.message}`, 'error');
  } finally {
    // Limpiar tras el diálogo de impresión para no dejar residuos en DOM.
    const area = $('area-impresion');
    if (area) area.innerHTML = '';
  }
}

/** Carga el historial y lo pinta en la tabla. */
async function cargarHistorial() {
  const cargando = $('historial-cargando');
  const error = $('historial-error');
  cargando.classList.remove('hidden');
  error.classList.add('hidden');
  const btn = $('btn-refrescar');
  if (btn) btn.disabled = true;

  try {
    const arqueos = await api.cashHistory(100);
    renderHistorial(arqueos || []);
    cargando.classList.add('hidden');
  } catch (e) {
    cargando.classList.add('hidden');
    error.textContent = `No se pudo cargar el historial: ${e.message}`;
    error.classList.remove('hidden');
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ---- Inicialización bajo guardia de seguridad ----
async function init() {
  if (window.authGuardReady) await window.authGuardReady;

  $('btn-refrescar').addEventListener('click', cargarHistorial);

  // Filtro por fecha de cierre (client-side, tiempo real).
  const filtroFecha = $('filtro-fecha');
  if (filtroFecha) {
    filtroFecha.addEventListener('input', filtrarHistorial);
    filtroFecha.addEventListener('change', filtrarHistorial);
  }
  const btnLimpiar = $('btn-limpiar-fecha');
  if (btnLimpiar) {
    btnLimpiar.addEventListener('click', () => {
      if (filtroFecha) filtroFecha.value = '';
      filtrarHistorial();
    });
  }

  // Módulo ES: exponer la función en window para el `onclick` inline de las filas.
  window.imprimirResumenCaja = imprimirResumenCaja;

  await cargarHistorial();
}

init();
