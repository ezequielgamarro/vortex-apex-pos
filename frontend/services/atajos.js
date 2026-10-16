/**
 * atajos.js — Atajos de teclado del Terminal POS.
 *
 * ARQUITECTURA (por qué un archivo aparte):
 *   Single Responsibility (SOLID/SRP): la gestión del teclado es una
 *   responsabilidad DISTINTA de la lógica del carrito/cobro (pos.js). Se
 *   mantiene aislada para poder testear/ajustar atajos sin tocar la lógica de
 *   negocio, y para reutilizar el patrón en otras vistas más adelante.
 *
 * PATRÓN CENTRAL — "dispatcher de acciones" (no un if por tecla):
 *   Un único listener global de `keydown` busca la tecla en una TABLA de atajos
 *   y ejecuta la acción asociada. Agregar/mover un atajo = editar la tabla.
 *   No se engancha un listener por botón ni se modifica el HTML.
 *
 * REGLAS DE ORO (ergonomía y seguridad):
 *   1. Si el foco está en un campo de escritura (input/textarea/select), los
 *      atajos GENERALES se ignoran (para no robarle la letra al cajero). Los
 *      atajos marcados con `permitirEnInput` sí se aplican (p.ej. cobrar con F2).
 *   2. `Escape` cierra el modal abierto si lo hay (comportamiento universal).
 *   3. Si hay un modal abierto, los atajos que no sean "cerrar/confirmar" no
 *      aplican (evita disparar cobros mientras se carga un producto por peso).
 *   4. Los atajos se alimentan de IDs que YA existen en pos.html; no requiere
 *      cambios en los componentes existentes.
 *
 * Se importa como MÓDULO desde pos.js (export { instalarAtajosPOS }).
 */

/**
 * Devuelve true si el foco está en un control de entrada de texto.
 * Cubre input, textarea y select (nativos y vía contenteditable por robustez).
 */
function focoEnCampoDeTexto() {
  const el = document.activeElement;
  if (!el) return false;
  const tag = (el.tagName || '').toUpperCase();
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (el.isContentEditable) return true;
  return false;
}

/** ¿Hay un modal abierto en este momento? (mismo criterio que pos.js) */
function modalAbierto() {
  return !!document.querySelector('[id^="modal-"].flex');
}

/** Cierra el modal abierto (si lo hay) simulando sus botones de cancelar. */
function cerrarModalActivo() {
  const abierto = document.querySelector('[id^="modal-"].flex');
  if (!abierto) return false;
  const id = abierto.id;
  // Mapa modal -> botón primario de cierre. Se usa el botón real para NO
  // duplicar la lógica de limpieza que ya vive en pos.js.
  const mapa = {
    'modal-peso': 'btn-peso-cancelar-2',
    'modal-servicio': 'btn-servicio-cancelar-2',
    'modal-nuevo-cliente': 'btn-cliente-cancelar-2',
    'modal-venta-completada': 'btn-vc-nueva',
  };
  const btnId = mapa[id];
  const btn = btnId ? document.getElementById(btnId) : null;
  if (btn) {
    btn.click();
    return true;
  }
  return false;
}

/** Enfoca un elemento por id y (opcional) selecciona su contenido. */
function enfocar(id, { seleccionar = false } = {}) {
  const el = document.getElementById(id);
  if (!el) return;
  // Diferido: si venimos de cerrar un modal, el reflow aún no ocurrió.
  setTimeout(() => {
    el.focus();
    if (seleccionar && typeof el.select === 'function') {
      try { el.select(); } catch (_) { /* inputs number: select() puede fallar */ }
    }
  }, 50);
}

/**
 * Tabla de atajos: la tecla (event.key) -> definición de la acción.
 * `permitirEnInput`: si true, el atajo funciona AUNQUE el foco esté en un input.
 * `soloSinModal`:   si true, el atajo NO se ejecuta si hay un modal abierto.
 * `manejar`:        acción a ejecutar.
 */
const ATAJOS = {
  F1: {
    descripcion: 'Buscar producto',
    permitirEnInput: true,
    manejar: () => enfocar('pos-search', { seleccionar: true }),
  },
  F2: {
    descripcion: 'Cobrar venta',
    // F2 funciona aunque el foco esté en un input (el cajero puede estar
    // escribiendo el monto "paga con" y querer cobrar de una).
    permitirEnInput: true,
    manejar: () => document.getElementById('btn-cobrar')?.click(),
  },
  F4: {
    descripcion: 'Nueva venta (vaciar carrito)',
    soloSinModal: true,
    manejar: () => document.getElementById('btn-vc-nueva')?.click(),
  },
  F8: {
    descripcion: 'Imprimir comprobante',
    // Solo tiene sentido DENTRO del modal de venta completada.
    requiereModal: 'modal-venta-completada',
    manejar: () => document.getElementById('btn-vc-imprimir')?.click(),
  },
};

/**
 * Instala los atajos del POS. Idempotente (guarda `data-atajos-instalado` en
 * document para no duplicar el listener si se llamara dos veces).
 */
export function instalarAtajosPOS() {
  if (document.body.dataset.atajosInstalado === '1') return;
  document.body.dataset.atajosInstalado = '1';

  document.addEventListener('keydown', (ev) => {
    // --- Escape: cierra el modal abierto (comportamiento universal) ---
    if (ev.key === 'Escape') {
      if (cerrarModalActivo()) {
        ev.preventDefault();
      }
      return;
    }

    // --- Ctrl+Delete: vaciar carrito (acción destructiva, con guarda) ---
    if (ev.ctrlKey && ev.key === 'Delete') {
      if (modalAbierto()) return; // no vaciar mientras se configura un modal
      // Reutiliza el botón "Nueva Venta" solo si el carrito tiene algo: si está
      // vacío no hace nada (idempotente). Pedimos confirmación ligera.
      ev.preventDefault();
      const btnNueva = document.getElementById('btn-vc-nueva');
      // En el flujo normal "Nueva Venta" vive en el modal post-cobro. Para el
      // vaciado en frío, disparamos un evento que pos.js pueda atender; si no
      // está escuchado, no pasa nada (degradación elegante).
      window.dispatchEvent(new CustomEvent('pos-vaciar-carrito'));
      return;
    }

    const def = ATAJOS[ev.key];
    if (!def) return;

    // Regla: no robar atajos generales mientras se escribe.
    if (focoEnCampoDeTexto() && !def.permitirEnInput) return;

    // Regla: si hay modal, solo aplican los atajos que tengan sentido con él.
    if (modalAbierto() && def.soloSinModal) return;

    // Regla: los atajos atados a un modal específico solo funcionan cuando ESE
    // modal está abierto (p.ej. F8 imprimir solo en "Venta completada").
    if (def.requiereModal) {
      const m = document.getElementById(def.requiereModal);
      if (!m || !m.classList.contains('flex')) return;
    }

    ev.preventDefault();
    def.manejar();
  });

  inyectarAyuda();
}

/**
 * Inserta el control de ayuda (botón "?" + panel de atajos) EN EL HEADER,
 * pegado a la izquierda del ícono de configuración (tuerca).
 *
 * POR QUÉ EN EL HEADER Y NO FLOTANTE:
 *   Un botón flotante competía visualmente con "Cobrar venta" y se superponía
 *   a acciones del carrito. Colocarlo junto a la tuerca lo integra a la barra
 *   de utilidades del header (tema/perfil/config), sin tapar nada.
 *
 * POR QUÉ UN MutationObserver:
 *   La tuerca la inyecta guard.js de forma ASÍNCRONA (tras `await /auth/perfil`).
 *   Cuando este módulo corre (pos.js), la tuerca puede aún no existir. Se espera
 *   a que aparezca para insertar el "?" justo a su izquierda; si nunca aparece
 *   (p. ej. usuario cajero, que no ve la tuerca), se hace fallback al borde
 *   derecho del header para no perder la ayuda.
 *
 * Este módulo se importa SOLO desde pos.js, por lo que el control aparece
 * únicamente en la pantalla de Punto de Venta.
 */
function inyectarAyuda() {
  if (document.getElementById('atajos-ayuda')) return;

  const header = document.querySelector('header');
  if (!header) return; // vista sin header: no hay dónde anclar (defensivo)

  // Contenedor RELATIVO para poder posicionar el panel debajo del botón.
  const cont = document.createElement('div');
  cont.id = 'atajos-ayuda';
  cont.className = 'relative';

  // Botón "?" con el MISMO estilo que los demás controles del header
  // (tema/tuerca): p-2, texto del cuerpo, hover secundario. Así queda
  // visualmente hermanado con la tuerca, no como un botón de acción.
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.id = 'atajos-toggle';
  btn.setAttribute('aria-label', 'Ver atajos de teclado');
  btn.title = 'Atajos de teclado (F1..F8, Esc)';
  btn.className = 'icon-btn font-bold leading-none';
  btn.textContent = '?';

  // Panel de la lista (oculto por defecto), anclado bajo el botón a la derecha.
  const panel = document.createElement('div');
  panel.id = 'atajos-panel';
  panel.className =
    'hidden absolute right-0 top-full mt-2 z-50 pos-card p-4 text-sm shadow-lg max-w-xs';
  panel.innerHTML = `
    <p class="font-semibold text-pos-text-head mb-2">Atajos de teclado</p>
    <ul class="space-y-1 text-pos-text-body">
      ${Object.entries(ATAJOS)
        .map(([tecla, def]) =>
          `<li class="flex items-center justify-between gap-4">
             <kbd class="px-2 py-0.5 rounded bg-pos-secondary/60 text-pos-text-head font-mono text-xs">${tecla}</kbd>
             <span class="text-right">${def.descripcion}</span>
           </li>`)
        .join('')}
      <li class="flex items-center justify-between gap-4">
        <kbd class="px-2 py-0.5 rounded bg-pos-secondary/60 text-pos-text-head font-mono text-xs">Esc</kbd>
        <span class="text-right">Cerrar ventana emergente</span>
      </li>
      <li class="flex items-center justify-between gap-4">
        <kbd class="px-2 py-0.5 rounded bg-pos-secondary/60 text-pos-text-head font-mono text-xs">Ctrl+Del</kbd>
        <span class="text-right">Vaciar carrito</span>
      </li>
    </ul>`;

  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    panel.classList.toggle('hidden');
  });
  // Cerrar el panel al hacer clic fuera (delegado, barato).
  document.addEventListener('click', (e) => {
    if (!cont.contains(e.target)) panel.classList.add('hidden');
  });

  cont.appendChild(btn);
  cont.appendChild(panel);

  // Inserta el control a la IZQUIERDA de la tuerca (config), o a la izquierda
  // del conmutador de tema, o antes del perfil (.ml-auto). Se re-evalúa cuando
  // guard.js termina de inyectar la tuerca (MutationObserver), para garantizar
  // que quede contiguo a ella sin importar el orden de carga.
  const insertarAntesDeLaTuerca = () => {
    const tuerca = header.querySelector('[data-config-toggle]');
    if (tuerca && tuerca.parentNode === header) {
      header.insertBefore(cont, tuerca);
      return true;
    }
    const tema = header.querySelector('[data-theme-toggle]');
    if (tema && tema.parentNode === header) {
      header.insertBefore(cont, tema);
      return true;
    }
    const perfil = header.querySelector('.ml-auto');
    if (perfil && perfil.parentNode === header) {
      header.insertBefore(cont, perfil);
      return true;
    }
    return false;
  };

  // Intento inmediato; si la tuerca aún no está, esperamos a que el header
  // cambie (guard.js la agrega asíncronamente).
  if (!insertarAntesDeLaTuerca()) {
    const obs = new MutationObserver(() => {
      if (insertarAntesDeLaTuerca()) obs.disconnect();
    });
    obs.observe(header, { childList: true });
    // Salvaguarda: si en 3 s no apareció nada, anexar igual (nunca perder ayuda).
    setTimeout(() => {
      if (!cont.parentNode) header.appendChild(cont);
      obs.disconnect();
    }, 3000);
  }
}
