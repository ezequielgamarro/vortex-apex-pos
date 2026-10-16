/**
 * sidebar.js — Menú lateral desplegable (móvil). Script clásico, sin módulos.
 * Antes vivía en un <script> dentro de cada HTML; se movió a un archivo para
 * poder usar una Content-Security-Policy que no permite scripts en línea.
 */
(function () {
  const menu = document.getElementById('menu-toggle');
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  function closeS() { sidebar?.classList.add('-translate-x-full'); overlay?.classList.add('hidden'); }
  function openS() { sidebar?.classList.remove('-translate-x-full'); overlay?.classList.remove('hidden'); }
  menu?.addEventListener('click', () => sidebar?.classList.contains('-translate-x-full') ? openS() : closeS());
  overlay?.addEventListener('click', closeS);
})();
