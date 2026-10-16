/**
 * index-redirect.js — Punto de entrada de la app:
 *  - Con sesión activa → Reportes (admin) o Punto de Venta (cajero).
 *  - Sin sesión        → login.html.
 * (Movido desde un <script> en línea de index.html para cumplir la CSP.)
 */
(function () {
  if (localStorage.getItem('token')) {
    var rol = localStorage.getItem('rol');
    window.location.replace(rol === 'admin' ? 'reportes.html' : 'pos.html');
  } else {
    window.location.replace('login.html');
  }
})();
