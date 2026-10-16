/**
 * modal-close.js — Cierre genérico de modales: cualquier elemento con el
 * atributo `data-close` dentro de un contenedor `id="modal..."` lo oculta.
 * (Movido desde un <script> en línea para cumplir la CSP.)
 */
document.addEventListener('click', (e) => {
  if (e.target.closest('[data-close]')) {
    const m = e.target.closest('[id^="modal"]');
    if (m) { m.classList.add('hidden'); m.classList.remove('flex'); }
  }
});
