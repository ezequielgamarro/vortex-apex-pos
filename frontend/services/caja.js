/**
 * caja.js — Lógica del Arqueo de Caja.
 * Consulta la caja activa, permite abrir, registrar movimientos y cerrar el turno.
 */
import { api } from './api.js';
import { mostrarAlerta } from './ui.js';

const $ = (id) => document.getElementById(id);

const money = (n) =>
  new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP' }).format(n || 0);

const fmtDate = (iso) => {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString('es-CL', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
};

// Estado en memoria del último resumen de caja (para el cálculo del cierre).
let ultimoResumen = null;
let cajaAbierta = false;
let refrecarTimer = null;
const INTERVALO_REFRESCO_MS = 20000; // panel "tiempo real" con el backend


function modal(id, abrir = true) {
  const m = document.getElementById(id);
  if (!m) return;
  if (abrir) { m.classList.remove('hidden'); m.classList.add('flex'); }
  else { m.classList.add('hidden'); m.classList.remove('flex'); }
}

/** Renderiza el estado de la caja según si está abierta o cerrada. */
function renderEstado(abierta) {
  cajaAbierta = Boolean(abierta);
  const indicador = $('indicador-estado');
  const texto = $('texto-estado');
  const puntos = ['btn-movimiento', 'btn-cerrar'];

  if (cajaAbierta) {
    // Verde = caja abierta (semántica universal "activo/ok"); más claro en dark.
    indicador.className = 'h-3 w-3 rounded-full bg-green-500 dark:bg-green-400';
    texto.textContent = 'Abierta';
    $('btn-abrir').classList.add('hidden');
    puntos.forEach((id) => document.getElementById(id).classList.remove('hidden'));
  } else {
    indicador.className = 'h-3 w-3 rounded-full bg-pos-secondary';
    texto.textContent = 'Cerrada';
    $('btn-abrir').classList.remove('hidden');
    puntos.forEach((id) => document.getElementById(id).classList.add('hidden'));
  }

  // Auto-refresco sólo mientras la caja está abierta (no molesta cuando no hay turno).
  if (refrecarTimer) { clearInterval(refrecarTimer); refrecarTimer = null; }
  if (cajaAbierta) {
    refrecarTimer = setInterval(() => { cargar(); }, INTERVALO_REFRESCO_MS);
  }
}

/** Actualiza la etiqueta del panel de resumen (ec. de caja en tiempo real). */
function actualizarPanelInicial() {
  const inicial = Number(ultimoResumen?.monto_inicial ?? 0);
  const ventas = Number(ultimoResumen?.ventas_efectivo ?? 0);
  const esperado = Number(ultimoResumen?.total_esperado ?? 0);
  if ($('texto-ecuacion')) {
    $('texto-ecuacion').textContent =
      `${money(inicial)} (inicial) + ${money(ventas)} (ventas efectivo) = ${money(esperado)} (total esperado)`;
  }
}


/** Renderiza los totales financieros y movimientos desde el resumen. */
function renderResumen(resumen) {
  if (!resumen) return;
  ultimoResumen = resumen;
  if ($('fin-inicial')) $('fin-inicial').textContent = money(resumen.monto_inicial);
  $('fin-ventas').textContent = money(resumen.ventas_efectivo);
  $('fin-ingresos').textContent = money(resumen.ingresos_manuales);
  $('fin-egresos').textContent = money(-resumen.egresos_manuales);
  $('fin-esperado').textContent = money(resumen.total_esperado);
  // Fila informativa de Cuenta Corriente (se oculta si no hubo crédito en el turno).
  const credito = Number(resumen.ventas_credito || 0);
  const fila = $('fin-credito-fila');
  if (fila) {
    fila.classList.toggle('hidden', !(credito > 0));
    fila.classList.toggle('flex', credito > 0);
    if ($('fin-credito')) $('fin-credito').textContent = money(credito);
  }
  actualizarPanelInicial();

  // Movimientos
  const tbody = $('movimientos-tabla');
  tbody.innerHTML = '';
  const movs = resumen.movimientos || [];
  if (!movs.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="text-center text-pos-text-body/60 py-6">Sin movimientos en el turno.</td></tr>';
    return;
  }
  movs.sort((a, b) => new Date(a.fecha) - new Date(b.fecha)).forEach((m) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><span class="badge ${m.tipo === 'ingreso' ? 'badge-primary' : 'badge-danger'}">${m.tipo}</span></td>
      <td>${m.concepto || '—'}</td>
      <td>${m.metodo_pago || '—'}</td>
      <td>${fmtDate(m.fecha)}</td>
      <td class="text-right font-semibold ${m.tipo === 'ingreso' ? '' : 'text-pos-danger'}">${m.tipo === 'ingreso' ? '+' : '-'}${money(m.monto)}</td>`;
    tbody.appendChild(tr);
  });
}

/** Carga el estado global de la caja. */
async function cargar() {
  try {
    const resumen = await api.cashSummary();
    renderEstado(true);
    renderResumen(resumen);
  } catch (e) {
    // Si no hay caja abierta, el resumen falla con 409 -> caja cerrada
    ultimoResumen = null;
    renderEstado(false);
    if ($('fin-inicial')) $('fin-inicial').textContent = money(0);
    $('fin-ventas').textContent = money(0);
    $('fin-ingresos').textContent = money(0);
    $('fin-egresos').textContent = money(0);
    $('fin-esperado').textContent = money(0);
    const filaF = $('fin-credito-fila');
    if (filaF) { filaF.classList.remove('flex'); filaF.classList.add('hidden'); }
    if ($('texto-ecuacion')) $('texto-ecuacion').textContent = 'La caja está cerrada. Abre un turno para comenzar.';
    $('movimientos-tabla').innerHTML = '<tr><td colspan="5" class="text-center text-pos-text-body/60 py-6">La caja está cerrada.</td></tr>';
  }
}

// ---- Acciones ----
async function abrir(e) {
  e.preventDefault();
  const monto = Number($('monto-inicial').value);
  const observaciones = $('obs-apertura').value.trim() || null;
  try {
    await api.openCash({ monto_inicial: monto, observaciones });
    modal('modal-abrir', false);
    $('form-abrir').reset();
    await cargar();
  } catch (err) {
    mostrarAlerta(`Error: ${err.message}`, 'error');
  }
}

async function registrarMovimiento(e) {
  e.preventDefault();
  try {
    const mov = {
      tipo: $('mov-tipo').value,
      monto: Number($('mov-monto').value),
      concepto: $('mov-concepto').value.trim(),
      metodo_pago: $('mov-metodo').value,
    };
    await api.addMovement(mov);
    modal('modal-movimiento', false);
    $('form-movimiento').reset();
    await cargar();
  } catch (err) {
    mostrarAlerta(`Error: ${err.message}`, 'error');
  }
}

// ---- Flujo de cierre en DOS pasos ----
let montoRealPte = null;   // efectivo real contado por el cajero (pendiente confirmar)
let obsCierrePte = null;

/** Abre el modal de cierre (Paso 1): muestra total esperado y calcula diferencias. */
function abrirModalCierre() {
  const esperado = Number(ultimoResumen?.total_esperado ?? 0);
  $('cc-esperado').textContent = money(esperado);
  $('monto-real').value = '';
  $('obs-cierre').value = '';
  actualizarDiferencia();
  modal('modal-cerrar');
}

/** Recalcula en vivo la diferencia entre el efectivo contado y el total esperado. */
function actualizarDiferencia() {
  const esperado = Number(ultimoResumen?.total_esperado ?? 0);
  const real = Number($('monto-real').value) || 0;
  const diff = real - esperado;
  const el = $('cc-diff');
  if (!el) return;

  if ($('monto-real').value === '') {
    el.className = 'hidden';
    return;
  }
  el.className = 'rounded-lg px-3 py-2 text-sm font-medium flex items-center justify-between';
  let texto = '';
  if (Math.abs(diff) < 0.005) {
    el.className += ' bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300';
    texto = 'Cuadre exacto (sin diferencia)';
  } else if (diff > 0) {
    el.className += ' bg-violet-50 text-pos-primary dark:bg-pos-primary/15';
    texto = `Sobrante: ${money(diff)}`;
  } else {
    el.className += ' bg-red-50 text-pos-danger dark:bg-pos-danger/15';
    texto = `Faltante: ${money(Math.abs(diff))}`;
  }
  el.innerHTML = `<span>Sobrante o faltante:</span><span class="font-bold">${texto}</span>`;
}

/** Carga el avance del reporte en el modal de confirmación (Paso 2). */
function prepararConfirmacion() {
  montoRealPte = Number($('monto-real').value) || 0;
  obsCierrePte = $('obs-cierre').value.trim() || null;

  const r = {
    inicial: Number(ultimoResumen?.monto_inicial ?? 0),
    ventas: Number(ultimoResumen?.ventas_efectivo ?? 0),
    ingresos: Number(ultimoResumen?.ingresos_manuales ?? 0),
    egresos: Number(ultimoResumen?.egresos_manuales ?? 0),
    credito: Number(ultimoResumen?.ventas_credito ?? 0),
    esperado: Number(ultimoResumen?.total_esperado ?? 0),
    real: montoRealPte,
  };
  r.diff = r.real - r.esperado;

  if ($('resumen-cierre-tabla')) {
    const filaCredito = r.credito > 0
      ? `<tr><td class="py-2 text-pos-text-body/80">Ventas a Cuenta Corriente <span class="text-pos-text-body/50">— se cobran por Cuentas Corrientes</span></td><td class="py-2 text-right font-medium text-pos-text-body/80">${money(r.credito)}</td></tr>`
      : '';
    $('resumen-cierre-tabla').innerHTML = `
      <tbody class="divide-y divide-pos-secondary/30 text-sm">
        <tr><td class="py-2 text-pos-text-body/80">Fondo inicial</td><td class="py-2 text-right font-medium text-pos-text-head">${money(r.inicial)}</td></tr>
        <tr><td class="py-2 text-pos-text-body/80">Ventas en efectivo del turno</td><td class="py-2 text-right font-medium text-pos-text-head">${money(r.ventas)}</td></tr>
        <tr><td class="py-2 text-pos-text-body/80">Ingresos manuales</td><td class="py-2 text-right font-medium text-pos-text-head">+ ${money(r.ingresos)}</td></tr>
        <tr><td class="py-2 text-pos-text-body/80">Egresos manuales</td><td class="py-2 text-right font-medium text-pos-danger">- ${money(r.egresos)}</td></tr>
        ${filaCredito}
        <tr class="border-t border-pos-secondary/50 bg-pos-secondary/20"><td class="py-2 font-bold text-pos-text-head">Total esperado en caja</td><td class="py-2 text-right font-bold text-pos-primary">${money(r.esperado)}</td></tr>
        <tr><td class="py-2 text-pos-text-body/80">Efectivo real contado</td><td class="py-2 text-right font-medium text-emerald-600 dark:text-emerald-400">${money(r.real)}</td></tr>
      </tbody>`;
  }
  const diffBox = $('cierre-confirm-diff');
  if (diffBox) {
    const faltex = Math.abs(r.diff) < 0.005
      ? { txt: 'Sin diferencia', cls: 'badge-neutral' }
      : r.diff > 0
          ? { txt: `Sobrante ${money(r.diff)}`, cls: 'badge-primary' }
          : { txt: `Faltante ${money(Math.abs(r.diff))}`, cls: 'badge-danger' };
    diffBox.textContent = `${faltex.txt}`;
    diffBox.className = `badge ${faltex.cls} text-sm px-3 py-1`;
  }
  if ($('cierre-resumen-obs')) {
    $('cierre-resumen-obs').textContent = obsCierrePte
      ? `Observaciones: ${obsCierrePte}` : 'Sin observaciones.';
  }
  modal('modal-cerrar', false);
  modal('modal-cierre-confirm');
}

/** Ejecuta el cierre definitivo (usa los valores del reporte visualizado). */
async function confirmarCierre(e) {
  e.preventDefault();
  try {
    await api.closeCash({ monto_final: montoRealPte, observaciones: obsCierrePte });
    modal('modal-cierre-confirm', false);
    montoRealPte = null;
    obsCierrePte = null;
    await cargar();
  } catch (err) {
    mostrarAlerta(`Error al cerrar caja: ${err.message}`, 'error');
  }
}


// ---- Inicialización bajo guardia de seguridad ----
async function init() {
  if (window.authGuardReady) {
    await window.authGuardReady;
  }

  $('btn-abrir').addEventListener('click', () => modal('modal-abrir'));
  $('form-abrir').addEventListener('submit', abrir);
  $('btn-movimiento').addEventListener('click', () => modal('modal-movimiento'));
  $('form-movimiento').addEventListener('submit', registrarMovimiento);
  $('btn-cerrar').addEventListener('click', abrirModalCierre);
  // La apertura de 'monto-real' no envía; el cierre definitivo se confirma en el paso 2.
  const formPaso1 = $('form-cerrar');
  if (formPaso1) formPaso1.addEventListener('submit', (e) => e.preventDefault());
  $('monto-real').addEventListener('input', actualizarDiferencia);
  const btnSig = $('btn-cc-siguiente');
  if (btnSig) btnSig.addEventListener('click', prepararConfirmacion);
  const formConf = $('form-cierre-confirm');
  if (formConf) formConf.addEventListener('submit', confirmarCierre);

  await cargar();
}

init();
