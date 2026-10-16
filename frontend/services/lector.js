/**
 * lector.js — Lector de códigos de barras USB/Bluetooth (modo "teclado").
 *
 * Estos lectores "teclean" el código a gran velocidad y cierran con Enter
 * (o con Tab, que es el otro sufijo habitual).
 * Este módulo detecta esa ráfaga en todo el documento, para que la lectura
 * funcione aunque el foco no esté en el buscador, y la distingue del tipeo
 * humano por el intervalo entre teclas.
 *
 * Alcance deliberado:
 *   - Solo actúa cuando el foco NO está en un campo editable: en un campo la
 *     lectura ya escribe el código y cada pantalla resuelve el Enter por su
 *     cuenta (buscador del POS, buscador y campo de código del inventario).
 *   - Se ignora mientras hay un modal abierto.
 */

/** Intervalo máximo entre teclas para considerarlas parte de una misma ráfaga. */
const GAP_MAX_MS = 50;
/** Largo mínimo para tratar una ráfaga como código (evita falsos positivos). */
const LARGO_MIN = 4;

/** Quita caracteres de control y espacios de los extremos. */
export function normalizarCodigo(s) {
  return String(s ?? '').replace(/[\u0000-\u001f\u007f]/g, '').trim();
}

/** ¿El elemento permite escribir texto? */
export function esCampoEditable(el) {
  if (!el || el === document.body) return false;
  const tag = el.tagName;
  if (tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (tag === 'INPUT') {
    const t = (el.getAttribute('type') || 'text').toLowerCase();
    return !['button', 'submit', 'reset', 'checkbox', 'radio', 'file', 'image'].includes(t);
  }
  return !!el.isContentEditable;
}

/** ¿Hay algún modal abierto? (mismo criterio que pos.js e inventario.js) */
function hayModalAbierto() {
  return !!document.querySelector('[id^="modal-"].flex');
}

/**
 * Instala el detector. `alEscanear(codigo)` recibe el código ya normalizado.
 * Devuelve una función para desinstalarlo.
 */
export function instalarLector(alEscanear) {
  let buffer = '';
  let ultimaTecla = 0;
  let enRafaga = false;

  const reiniciar = () => {
    buffer = '';
    enRafaga = false;
  };

  const alTeclear = (ev) => {
    if (ev.ctrlKey || ev.altKey || ev.metaKey) return;
    if (esCampoEditable(document.activeElement) || hayModalAbierto()) {
      reiniciar();
      return;
    }

    const ahora = performance.now();

    // Tab solo cierra una lectura si llega pegado a la última tecla: así un Tab
    // humano (navegar con el teclado) nunca se confunde con el sufijo del lector.
    const cierraConTab = ev.key === 'Tab' && ahora - ultimaTecla <= GAP_MAX_MS;
    if (ev.key === 'Enter' || cierraConTab) {
      const codigo = normalizarCodigo(buffer);
      const esLectura = enRafaga && codigo.length >= LARGO_MIN;
      reiniciar();
      if (esLectura) {
        ev.preventDefault();
        ev.stopPropagation();
        alEscanear(codigo);
      }
      return;
    }

    if (ev.key.length !== 1) return; // Shift, flechas, F-keys, etc.

    if (buffer && ahora - ultimaTecla > GAP_MAX_MS) reiniciar();
    // Desde la 2.ª tecla en ráfaga se evita que un botón enfocado reaccione
    // (p. ej. la barra espaciadora haría clic).
    if (buffer) {
      enRafaga = true;
      ev.preventDefault();
    }
    buffer += ev.key;
    ultimaTecla = ahora;
  };

  document.addEventListener('keydown', alTeclear, true);
  return () => document.removeEventListener('keydown', alTeclear, true);
}
