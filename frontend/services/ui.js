/**
 * ui.js — Sistema ÚNICO de notificaciones flotantes (alertas) del frontend.
 *
 * Single Source of Truth para la UI de alertas. Antes vivía duplicado dentro de
 * pos.js (como `window.mostrarAlerta` con facade implícito). Ese acoplamiento
 * era frágil: caja.js / inventario.js / usuarios.js / cuentas.js / auth.js NO
 * importan pos.js, por lo que `window.mostrarAlerta` podía ser `undefined` en
 * esas vistas. Este módulo desacopla la dependencia: cada vista importa `ui.js`.
 *
 * Contrato:
 *   - `mostrarAlerta(mensaje, tipo, opts)` → notificación no bloqueante.
 *   - `restaurarFocoSiLibre(destino, delay)` → restituye el foco SIN robarlo.
 *
 * El manejo de foco replica el patrón verificado en pos.js (bug: "tras cerrar
 * una alerta no puedo escribir"):
 *   1. Se captura el foco de ORIGEN antes de mostrar la alerta.
 *   2. Se permite un DESTINO PREFERIDO explícito (p. ej. el input a corregir).
 *   3. Al cerrar, se restituye el foco SOLO si quedó "libre" (el usuario no
 *      eligió otro control mientras tanto) → nunca se roba el foco.
 *
 * Sin dependencias externas (vanilla ESM). Usa los tokens del design system POS
 * (--pos-* definidos en css/tailwind.css).
 */

/** Tipos válidos de alerta (semántica visual). */
const TIPOS_VALIDOS = new Set(['ok', 'error', 'warn']);

/** Paletas de color por tipo, apoyadas en los tokens del design system. */
const PALETAS = {
  ok:    { borde: 'border-pos-success/50', icono: 'bg-pos-success/15 text-pos-success' },
  error: { borde: 'border-pos-danger/50',  icono: 'bg-pos-danger/15 text-pos-danger' },
  warn:  { borde: 'border-amber-400/60',   icono: 'bg-amber-400/20 text-amber-600 dark:text-amber-400' },
};

/** Paths SVG de los iconos por tipo (stroke=currentColor). */
const ICONOS = {
  ok:    '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>',
  error: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v4m0 4h.01M10.3 3.86L1.82 18a2 2 0 001.72 3h16.94a2 2 0 001.71-3L13.7 3.86a2 2 0 00-3.4 0z"/>',
  warn:  '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v4m0 4h.01M10.3 3.86L1.82 18a2 2 0 001.72 3h16.94a2 2 0 001.71-3L13.7 3.86a2 2 0 00-3.4 0z"/>',
};

/** ¿El foco del documento está "libre"? (en <body>, <html> o en ningún nodo). */
function focoLibre() {
  const activo = document.activeElement;
  return !activo || activo === document.body || activo === document.documentElement;
}

/**
 * Restituye el foco a un elemento SOLO si quedó libre (no roba el foco).
 * @param {Element|string|null} destino  Elemento o id a enfocar.
 * @param {number} [delay=0]  ms a diferir (0 = siguiente tick de layout).
 */
export function restaurarFocoSiLibre(destino, delay = 0) {
  const ejecutar = () => {
    if (!focoLibre()) return; // el usuario eligió otro foco → respetar
    const el = typeof destino === 'string' ? document.getElementById(destino) : destino;
    if (!el || !el.isConnected || el.disabled) return;
    if (typeof el.focus !== 'function') return;
    try { el.focus(); } catch (_) { /* no-op */ }
  };
  if (delay > 0) setTimeout(ejecutar, delay);
  else setTimeout(ejecutar, 0);
}

/** Devuelve (creándolo una vez) el contenedor raíz de las alertas. */
function contenedorRaiz() {
  let cont = document.getElementById('ui-alert-root');
  if (!cont) {
    cont = document.createElement('div');
    cont.id = 'ui-alert-root';
    cont.className =
      'fixed bottom-4 right-4 z-[80] flex flex-col items-end gap-2 max-w-sm w-full pointer-events-none';
    document.body.appendChild(cont);
  }
  return cont;
}

/**
 * Muestra una notificación flotante (toast) — reemplaza a `alert()` nativo.
 *
 * @param {string} mensaje                    Texto a mostrar.
 * @param {'ok'|'error'|'warn'} [tipo='ok']   Semántica visual.
 * @param {Object} [opts]
 * @param {string|Element} [opts.focoDestino] Destino PREFERIDO del foco al
 *   cerrar (p. ej. el input que el usuario debe corregir). Se enfoca solo si
 *   el foco quedó libre → no interrumpe al usuario si ya está escribiendo.
 * @param {number} [opts.duracionMs=4500]     Auto-cierre en ms.
 */
export function mostrarAlerta(mensaje, tipo = 'ok', opts = {}) {
  const t = TIPOS_VALIDOS.has(tipo) ? tipo : 'ok';
  const { focoDestino = null, duracionMs = 4500 } = opts;
  const pal = PALETAS[t];

  // (1) Captura del foco de origen ANTES de crear el toast.
  const focoOrigen = document.activeElement;
  // (2) Resolución del destino preferido (id → elemento).
  const elDestino =
    typeof focoDestino === 'string' ? document.getElementById(focoDestino) : focoDestino;

  const box = document.createElement('div');
  box.className =
    `pointer-events-auto w-full rounded-xl border shadow-lg p-4 flex items-start gap-3 bg-pos-bg dark:bg-gray-800 ${pal.borde} animate-toast-in`;
  box.setAttribute('role', 'alert');
  box.innerHTML = `
    <span class="shrink-0 flex items-center justify-center h-8 w-8 rounded-full ${pal.icono}">
      <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">${ICONOS[t]}</svg>
    </span>
    <p class="flex-1 text-sm font-medium text-pos-text-head dark:text-white leading-snug pt-1">${mensaje}</p>
    <button type="button" class="shrink-0 text-pos-text-body/50 hover:text-pos-text-head dark:hover:text-white" aria-label="Cerrar">
      <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
    </button>`;

  // (3) Cierre idempotente: restituye el foco sin robar el del usuario.
  let cerrado = false;
  const cerrar = () => {
    if (cerrado || !box.parentNode) return;
    cerrado = true;
    box.remove();
    // Preferencia: destino explícito (si sigue montado) > origen capturado.
    const objetivo = (elDestino && elDestino.isConnected) ? elDestino : focoOrigen;
    restaurarFocoSiLibre(objetivo, 0);
  };
  box.querySelector('button').addEventListener('click', cerrar);
  setTimeout(cerrar, duracionMs); // auto-cierre

  contenedorRaiz().appendChild(box);
}

/**
 * Expone la API en `window` para scripts NO-módulo (handlers inline, etc.).
 * Idempotente. Se invoca una vez en el arranque de cada vista.
 */
export function exponerUIglobal() {
  window.mostrarAlerta = mostrarAlerta;
  window.restaurarFocoSiLibre = restaurarFocoSiLibre;
}
