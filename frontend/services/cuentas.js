/**
 * cuentas.js — Cuentas Corrientes de clientes.
 *
 * Recibe una lista de clientes con su `saldo_deuda`, permite:
 *   - registrar clientes nuevos,
 *   - ver el historial (cargos/abonos) de un cliente,
 *   - registrar abonos (requieren caja abierta; el dinero ingresa a la gaveta).
 *
 * Depende de api.js (authFetch) y guard.js (protección de la ruta).
 */
import { api } from './api.js';
import { mostrarAlerta, esc } from './ui.js';

const $ = (id) => document.getElementById(id);

const money = (n) =>
  new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP' }).format(n || 0);

let clientes = [];
let clienteSeleccionado = null; // para detalle/abono
let cajaAbierta = false;

async function estadoCaja() {
  try {
    const caja = await api.activeCash();
    cajaAbierta = !!caja && (caja.estado || 'abierto') === 'abierto';
  } catch (_) {
    cajaAbierta = false;
  }
  const aviso = $('aviso-caja');
  if (aviso) aviso.classList.toggle('hidden', cajaAbierta);
}

function actualizarKpis() {
  $('kpi-clientes').textContent = String(clientes.length);
  const deudores = clientes.filter((c) => Number(c.saldo_deuda || 0) > 0);
  $('kpi-deudores').textContent = String(deudores.length);
  const total = deudores.reduce((acc, c) => acc + Number(c.saldo_deuda || 0), 0);
  $('kpi-deuda-total').textContent = money(total);
}

function renderTabla() {
  const tbody = $('tabla-clientes');
  tbody.innerHTML = '';
  if (!clientes.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="text-center text-pos-text-body/70 py-8">No hay clientes registrados.</td></tr>';
    return;
  }
  clientes.forEach((c) => {
    const saldo = Number(c.saldo_deuda || 0);
    const badgeSaldo = saldo > 0 ? 'badge-danger' : 'badge-neutral';
    const tr = document.createElement('tr');
    // Guardamos el nombre (y teléfono) como data-* para el filtro client-side:
    // el texto mostrado puede tener formato, pero el filtro usa el valor crudo.
    tr.dataset.nombre = (c.nombre || '').toLowerCase();
    tr.dataset.telefono = (c.telefono || '').toLowerCase();
    tr.innerHTML = `
      <td class="font-medium text-pos-text-head">${esc(c.nombre)}</td>
      <td>${esc(c.telefono || '—')}</td>
      <td class="text-right">
        <span class="badge ${badgeSaldo}">${money(saldo)}</span>
      </td>
      <td>
        <div class="flex justify-end gap-2">
          <button data-detalle="${c.id}" class="btn-secondary !px-3 !py-1.5 text-xs">Detalle</button>
          <button data-abono="${c.id}" class="btn-primary !px-3 !py-1.5 text-xs" ${saldo <= 0 ? 'disabled title="Sin deuda pendiente"' : ''}>Abonar</button>
        </div>
      </td>`;
    tbody.appendChild(tr);
  });
  tbody.querySelectorAll('[data-detalle]').forEach((b) =>
    b.addEventListener('click', () => verDetalle(Number(b.dataset.detalle))));
  tbody.querySelectorAll('[data-abono]').forEach((b) =>
    b.addEventListener('click', () => abrirAbono(Number(b.dataset.abono))));

  // Re-aplicar el filtro vigente tras un re-render (p. ej. al crear un cliente),
  // para no perder el estado de búsqueda del usuario.
  filtrarClientes();
}

/**
 * Filtro client-side sobre la tabla de clientes ya renderizada.
 * Oculta las filas cuyo nombre/teléfono no contengan el texto buscado
 * (comparación insensible a mayúsculas vía .toLowerCase()).
 */
function filtrarClientes() {
  const input = $('buscar-cliente');
  if (!input) return;
  const q = (input.value || '').trim().toLowerCase();
  const filas = $('tabla-clientes').querySelectorAll('tr[data-nombre]');
  let visibles = 0;
  filas.forEach((tr) => {
    const coincide = !q || tr.dataset.nombre.includes(q) || tr.dataset.telefono.includes(q);
    tr.style.display = coincide ? '' : 'none';
    if (coincide) visibles += 1;
  });
  // Mensaje informativo cuando el filtro no arroja coincidencias.
  actualizarAvisoSinResultados(q, visibles);
}

/** Muestra/oculta un aviso "sin resultados" respetando el filtro activo. */
function actualizarAvisoSinResultados(q, visibles) {
  const tbody = $('tabla-clientes');
  let aviso = tbody.querySelector('[data-sin-resultados]');
  const hayClientes = clientes.length > 0;
  const debeMostrar = hayClientes && visibles === 0 && !!q;
  if (debeMostrar && !aviso) {
    const tr = document.createElement('tr');
    tr.dataset.sinResultados = '1';
    tr.innerHTML = `<td colspan="4" class="text-center text-pos-text-body/70 py-8">Sin coincidencias para "${esc(q)}".</td>`;
    tbody.appendChild(tr);
  } else if (!debeMostrar && aviso) {
    aviso.remove();
  }
}

async function cargar() {
  try {
    const arr = await api.getClients(false);
    clientes = Array.isArray(arr) ? arr : [];
    actualizarKpis();
    renderTabla();
  } catch (e) {
    $('tabla-clientes').innerHTML =
      `<tr><td colspan="4" class="text-center text-pos-danger py-8">No se pudieron cargar los clientes: ${esc(e.message)}</td></tr>`;
  }
}

// ---- Crear cliente ----
function abrirNuevoCliente() {
  $('cli-nombre').value = '';
  $('cli-telefono').value = '';
  $('modal-cliente').classList.remove('hidden');
  $('modal-cliente').classList.add('flex');
  $('cli-nombre').focus();
}

async function guardarCliente() {
  const nombre = ($('cli-nombre').value || '').trim();
  if (!nombre) { mostrarAlerta('El nombre es obligatorio.', 'error', { focoDestino: 'cli-nombre' }); return; }
  try {
    await api.createClient({
      nombre,
      telefono: ($('cli-telefono').value || '').trim() || null,
    });
    $('modal-cliente').classList.add('hidden');
    $('modal-cliente').classList.remove('flex');
    await cargar();
  } catch (err) {
    mostrarAlerta(`No se pudo registrar: ${err.message}`, 'error');
  }
}

// ---- Detalle / historial ----
async function verDetalle(id) {
  try {
    const c = await api.getClient(id);
    clienteSeleccionado = c;
    $('detalle-nombre').textContent = c.nombre;
    $('detalle-telefono').textContent = c.telefono ? `Tel: ${c.telefono}` : '';
    $('detalle-saldo').textContent = `Saldo deudor: ${money(c.saldo_deuda)}`;

    const cont = $('detalle-movimientos');
    const movs = (Array.isArray(c.movimientos) ? c.movimientos : []).slice();
    if (!movs.length) {
      cont.innerHTML = '<p class="text-sm text-pos-text-body/70">Sin movimientos.</p>';
    } else {
      cont.innerHTML =
        '<div class="flex items-center justify-between text-xs text-pos-text-body/70 font-semibold uppercase pb-2 border-b border-pos-secondary/30">' +
        '<span>Fecha</span><span>Tipo</span><span>Monto</span>' +
        '</div>';
      movs.forEach((m) => {
        const fecha = new Date(m.fecha).toLocaleString('es-CL');
        const esCargo = m.tipo === 'cargo';
        const fila = document.createElement('div');
        fila.className = 'flex items-center justify-between py-1.5 border-b border-pos-secondary/20 last:border-0';
        fila.innerHTML =
          `<span class="text-xs text-pos-text-body/70">${fecha}</span>` +
          `<span class="badge ${esCargo ? 'badge-danger' : 'badge-primary'}">${esCargo ? 'Cargo' : 'Abono'}</span>` +
          `<span class="font-semibold ${esCargo ? 'text-pos-danger' : 'text-pos-primary'}">${money(m.monto)}</span>`;
        cont.appendChild(fila);
      });
    }
    $('modal-detalle').classList.remove('hidden');
    $('modal-detalle').classList.add('flex');
  } catch (err) {
    mostrarAlerta(`No se pudo consultar el historial: ${err.message}`, 'error');
  }
}

// ---- Abono ----
function abrirAbono(id) {
  const c = clientes.find((x) => x.id === id);
  if (!c) return;
  clienteSeleccionado = c;
  $('abono-titulo').textContent = `Abono de ${c.nombre}`;
  $('abono-subtitulo').textContent = `Deuda actual: ${money(c.saldo_deuda)}`;
  $('abono-monto').value = num(c.saldo_deuda); // pre-carga el total adeudado
  $('abono-concepto').value = '';
  $('modal-abono').classList.remove('hidden');
  $('modal-abono').classList.add('flex');
  $('abono-monto').focus();
}

function num(v) {
  const n = Number(v || 0);
  return Number.isInteger(n) ? String(n) : String(n.toFixed(2));
}

async function guardarAbono() {
  if (!clienteSeleccionado) return;
  const monto = Number($('abono-monto').value || 0);
  if (!(monto > 0)) { mostrarAlerta('Ingresa un monto mayor a cero.', 'error', { focoDestino: 'abono-monto' }); return; }
  if (!cajaAbierta) {
    mostrarAlerta('Para registrar el abono la caja debe estar abierta (el dinero ingresará como efectivo al turno). Abrí la caja en Control de Caja.', 'warn');
    return;
  }
  try {
    await api.registerAbono(clienteSeleccionado.id, {
      monto,
      concepto: ($('abono-concepto').value || '').trim() || null,
    });
    $('modal-abono').classList.add('hidden');
    $('modal-abono').classList.remove('flex');
    clienteSeleccionado = null;
    await cargar();
  } catch (err) {
    mostrarAlerta(`No se pudo registrar el abono: ${err.message}`, 'error');
  }
}

// ---- Inicialización bajo guardia ----
async function init() {
  if (window.authGuardReady) await window.authGuardReady;

  $('btn-nuevo-cliente').addEventListener('click', abrirNuevoCliente);
  $('btn-cli-guardar').addEventListener('click', guardarCliente);
  $('btn-abono-guardar').addEventListener('click', guardarAbono);

  // Filtro de clientes en tiempo real (client-side, sin ir al backend).
  const buscador = $('buscar-cliente');
  if (buscador) buscador.addEventListener('input', filtrarClientes);

  await estadoCaja();
  await cargar();
}

init();
