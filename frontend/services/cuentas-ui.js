/**
 * cuentas-ui.js — Cierre de los modales de Cuentas Corrientes (botones con
 * data-close-c / data-close-d / data-close-a). Movido desde un <script> en
 * línea del HTML para cumplir la CSP.
 */
document.querySelectorAll('[data-close-c],[data-close-d],[data-close-a]').forEach((b) =>
  b.addEventListener('click', (e) => {
    const m = e.target.closest('[id^="modal"]');
    if (m) { m.classList.add('hidden'); m.classList.remove('flex'); }
  })
);
