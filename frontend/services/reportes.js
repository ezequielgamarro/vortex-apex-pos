/**
 * reportes.js — Dashboard de analítica de negocio (SOLO admin).
 *
 * Consume `GET /api/reportes/dashboard?agrupacion=&rango=` y dibuja con Chart.js:
 *   a) Barras: ventas por periodo (días o meses).
 *   b) Doughnut: distribución de ingresos por método de pago.
 *   c) Barras horizontales: top 5 productos por cantidad.
 *
 * RBAC: la vista está protegida en 3 capas — menú (soloAdmin en guard.js),
 * ruta (RUTAS_SOLO_ADMIN en guard.js) y API (requiere_rol("admin") en el
 * backend). Este módulo no necesita re-validar el rol, pero el backend
 * devolverá 403 si un no-admin intentara llegar aquí.
 *
 * Depende de api.js (authFetch) y guard.js (protección de ruta + Chart global).
 */
import { api } from './api.js';

const $ = (id) => document.getElementById(id);

const money = (n) =>
  new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP' }).format(Number(n) || 0);

/** Etiqueta corta para el eje temporal: 'YYYY-MM-DD' → 'DD/MM'; 'YYYY-MM' → 'MMM YY'. */
function etiquetaPeriodo(periodo, agrupacion) {
  if (agrupacion === 'meses') {
    const [y, m] = periodo.split('-').map(Number);
    const d = new Date(y, (m || 1) - 1, 1);
    return d.toLocaleDateString('es-CL', { month: 'short', year: '2-digit' });
  }
  const [y, m, d] = periodo.split('-').map(Number);
  const fecha = new Date(y, (m || 1) - 1, d || 1);
  return fecha.toLocaleDateString('es-CL', { day: '2-digit', month: '2-digit' });
}

/** Etiqueta legible de un método de pago. */
const METODO_LABEL = {
  efectivo: 'Efectivo',
  tarjeta: 'Tarjeta',
  transferencia: 'Transferencia',
  mixto: 'Mixto',
  cuenta_corriente: 'Cuenta Corriente',
};
const metodoLabel = (m) => METODO_LABEL[m] || m || '—';

// Colores del Design System (se reutilizan para los datasets de Chart.js).
// Los colores de encabezados/grid/leyendas son theme-aware: se resuelven en
// cada render leyendo el tema activo (window.theme), para que sean legibles
// tanto en claro como en oscuro.
const COLOR_PRIMARY = '#6246ea';
const COLOR_DANGER = '#e45858';
const PALETA = [COLOR_PRIMARY, '#12a594', '#e8a93a', COLOR_DANGER, '#9b8cff'];

if (window.Chart) { window.Chart.defaults.font.family = '"Onest", system-ui, sans-serif'; }

/** ¿Tema oscuro activo? (vía window.theme; fallback: clase en <html>). */
function esTemaOscuro() {
  if (window.theme && typeof window.theme.actual === 'function') {
    return window.theme.actual() === 'dark';
  }
  return document.documentElement.classList.contains('dark');
}

/** Devuelve los colores de texto/grid/leyenda según el tema activo. */
function coloresTema() {
  return esTemaOscuro()
    ? { texto: '#c0c1d2', grid: 'rgba(192,193,210,0.12)', borde: '#191a25', primario: '#8e7bff' }
    : { texto: '#343548', grid: 'rgba(52,53,72,0.08)', borde: '#ffffff', primario: COLOR_PRIMARY };
}

// Instancias de Chart.js (se destruyen antes de recrear para evitar fugas).
let chartVentas = null;
let chartMetodos = null;
let chartTop = null;

// Última data cargada: permite REDIBUJAR los gráficos al cambiar de tema
// sin volver a llamar a la API (los colores dependen del tema activo).
let ultimoDashboard = null;
let ultimaAgrupacion = 'dias';

/** Destruye un gráfico previo si existe (Chart.js no permite reusar el canvas). */
function destruir(chart) {
  if (chart && typeof chart.destroy === 'function') chart.destroy();
}

/** (a) Barras: ventas por periodo. */
function dibujarVentas(serie, agrupacion) {
  destruir(chartVentas);
  const ctx = $('grafico-ventas');
  if (!ctx) return;
  const c = coloresTema();
  chartVentas = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: serie.map((p) => etiquetaPeriodo(p.periodo, agrupacion)),
      datasets: [{
        label: 'Ventas ($)',
        data: serie.map((p) => Number(p.total) || 0),
        backgroundColor: c.primario,
        borderRadius: 6,
        maxBarThickness: 48,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (cc) => ` ${money(cc.parsed.y)}`,
            afterLabel: (cc) => {
              const punto = serie[cc.dataIndex];
              return punto ? ` ${punto.cantidad} ticket(s)` : '';
            },
          },
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: { color: c.texto, callback: (v) => money(v) },
          grid: { color: c.grid },
        },
        x: { ticks: { color: c.texto }, grid: { display: false } },
      },
    },
  });
}

/** (b) Doughnut: distribución de ingresos por método de pago. */
function dibujarMetodos(porMetodo) {
  destruir(chartMetodos);
  const canvas = $('grafico-metodos');
  const vacio = $('metodos-vacio');
  if (!canvas) return;

  const hayDatos = porMetodo.some((m) => Number(m.total) > 0);
  canvas.classList.toggle('hidden', !hayDatos);
  if (vacio) vacio.classList.toggle('hidden', hayDatos);
  if (!hayDatos) return;

  const c = coloresTema();
  chartMetodos = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: porMetodo.map((m) => metodoLabel(m.metodo_pago)),
      datasets: [{
        data: porMetodo.map((m) => Number(m.total) || 0),
        backgroundColor: porMetodo.map((_, i) => PALETA[i % PALETA.length]),
        borderColor: c.borde,
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { color: c.texto, boxWidth: 12, padding: 12 } },
        tooltip: {
          callbacks: {
            label: (cc) => ` ${money(cc.parsed)}`,
          },
        },
      },
      cutout: '58%',
    },
  });
}

/** (c) Barras horizontales: top 5 productos por cantidad. */
function dibujarTop(top) {
  destruir(chartTop);
  const canvas = $('grafico-top');
  const vacio = $('top-vacio');
  if (!canvas) return;

  const hayDatos = top.length > 0;
  canvas.classList.toggle('hidden', !hayDatos);
  if (vacio) vacio.classList.toggle('hidden', hayDatos);
  if (!hayDatos) return;

  const c = coloresTema();
  chartTop = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: top.map((p) => p.nombre),
      datasets: [{
        label: 'Cantidad vendida',
        data: top.map((p) => Number(p.cantidad) || 0),
        backgroundColor: c.primario,
        borderRadius: 6,
        maxBarThickness: 28,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (cc) => ` ${cc.parsed.x} unidad(es) · ${money(top[cc.dataIndex]?.importe)}`,
          },
        },
      },
      scales: {
        x: { beginAtZero: true, ticks: { color: c.texto }, grid: { color: c.grid } },
        y: { ticks: { color: c.texto }, grid: { display: false } },
      },
    },
  });
}

/** Lee el selector de periodo y devuelve {agrupacion, rango}. */
function periodoSeleccionado() {
  const sel = $('filtro-agrupacion');
  const raw = sel ? sel.value : 'dias:7';
  const [agrupacion, rango] = raw.split(':');
  return { agrupacion, rango: Number(rango) || 0 };
}

/** Carga el dashboard y redibuja los gráficos. */
async function cargar() {
  const cargando = $('reportes-cargando');
  const error = $('reportes-error');
  const btn = $('btn-refrescar');

  cargando.classList.remove('hidden');
  error.classList.add('hidden');
  if (btn) btn.disabled = true;

  const { agrupacion, rango } = periodoSeleccionado();

  try {
    const data = await api.dashboardAnalytics(agrupacion, rango);

    // KPIs
    const total = Number(data.ventas_totales) || 0;
    const tickets = Number(data.cantidad_ventas) || 0;
    $('kpi-ventas').textContent = money(total);
    $('kpi-tickets').textContent = String(tickets);
    $('kpi-promedio').textContent = money(tickets > 0 ? total / tickets : 0);

    // Cachear para poder redibujar al cambiar de tema (sin refetch).
    ultimoDashboard = data;
    ultimaAgrupacion = data.agrupacion || agrupacion;

    dibujarGraficos();

    cargando.classList.add('hidden');
  } catch (e) {
    cargando.classList.add('hidden');
    error.textContent = `No se pudieron cargar los reportes: ${e.message}`;
    error.classList.remove('hidden');
  } finally {
    if (btn) btn.disabled = false;
  }
}

/** Redibuja los 3 gráficos a partir de la última data cacheada. */
function dibujarGraficos() {
  if (!ultimoDashboard) return;
  dibujarVentas(ultimoDashboard.serie_ventas || [], ultimaAgrupacion);
  dibujarMetodos(ultimoDashboard.por_metodo_pago || []);
  dibujarTop(ultimoDashboard.top_productos || []);
}

// ---- Inicialización bajo guardia de seguridad ----
async function init() {
  if (window.authGuardReady) await window.authGuardReady;

  $('btn-refrescar').addEventListener('click', cargar);
  const sel = $('filtro-agrupacion');
  if (sel) sel.addEventListener('change', cargar);

  // Al cambiar de tema (guard.js añade/quita la clase `dark` en <html>),
  // redibujamos los gráficos con los colores del tema activo.
  const obs = new MutationObserver(() => dibujarGraficos());
  obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });

  await cargar();
}

init();
