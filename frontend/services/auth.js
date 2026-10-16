/**
 * auth.js — Autenticación local contra FastAPI (JWT).
 *
 * Script GLOBAL (no módulo) cargado en `login.html` DESPUÉS de `config.js`.
 * Reemplaza por completo la integración de Supabase Auth (público).
 *
 * No usa tokens de Supabase: se conecta al backend **local** FastAPI y usa
 * el token JWT HS256 que este devuelve.
 *
 * Expone en `window`:
 *   - authAPI = { getToken, setToken, clearSession, login, logout, fetchProfile }
 *   - loginEmail(email, password)  (compatibilidad con <form> de login.html)
 *   - logout()
 */
(function () {
  'use strict';

  var TOKEN_KEY = 'token';
  var USER_KEY = 'user';

  function apiBase() {
    return window.API_BASE_URL || 'http://127.0.0.1:8000/api';
  }
  function getToken() { return localStorage.getItem(TOKEN_KEY); }
  function setToken(t) { localStorage.setItem(TOKEN_KEY, t); }
  function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem('rol');
  }

  /**
   * Consulta el perfil al backend con el token. Guarda y devuelve el perfil.
   * @returns {Promise<object|null>} { id, email, nombre, rol }
   */
  async function fetchProfile() {
    var token = getToken();
    if (!token) return null;
    try {
      var res = await fetch(apiBase() + '/auth/perfil', {
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + token,
        },
      });
      if (!res.ok) {
        if (res.status === 401 || res.status === 403) clearSession();
        return null;
      }
      var perfil = await res.json();
      localStorage.setItem(USER_KEY, JSON.stringify(perfil));
      localStorage.setItem('rol', perfil.rol || 'cajero');
      return perfil;
    } catch (err) {
      console.warn('[auth.js] No se pudo obtener el perfil:', err.message);
      return null;
    }
  }

  /**
   * Login local (formato OAuth2 urlencoded).
   * Guarda el access_token y devuelve el perfil.
   * @param {string} email
   * @param {string} password
   * @returns {Promise<object|null>}
   */
  async function login(email, password) {
    var body = new URLSearchParams();
    body.set('username', email);
    body.set('password', password);

    var res = await fetch(apiBase() + '/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
    });

    if (!res.ok) {
      var detail = 'Credenciales incorrectas';
      try { var b = await res.json(); if (b && b.detail) detail = b.detail; } catch (_) {}
      var err = new Error(detail);
      err.status = res.status;
      throw err;
    }

    var data = await res.json();
    if (!data || !data.access_token) {
      throw new Error('El servidor no devolvió un token de acceso');
    }
    setToken(data.access_token);
    return await fetchProfile();
  }

  /**
   * Pantalla de inicio según el rol del usuario.
   * Regla de negocio: la app abre en Reportes para admin; el cajero (sin
   * permiso de reportes) entra directamente al Punto de Venta.
   * @param {string} rol 'admin' | 'cajero' | undefined
   * @returns {string} ruta destino
   */
  function pantallaInicio(rol) {
    return rol === 'admin' ? 'reportes.html' : 'pos.html';
  }

  function logout() {
    clearSession();
    if (window.location.pathname.indexOf('login.html') === -1) {
      window.location.replace('login.html');
    }
  }

  // Compatibilidad con `loginEmail` (login.html)
  async function loginEmail(email, password) {
    return await login(email, password);
  }

  /**
   * Si la instalación está vacía (sin usuarios), el login no sirve: se lleva al
   * asistente de primer arranque. Un fallo de red se ignora (queda el login).
   */
  async function irAlAsistenteSiHaceFalta() {
    try {
      var res = await fetch(apiBase() + '/setup/estado');
      if (!res.ok) return;
      var estado = await res.json();
      if (estado && estado.necesita_setup) window.location.replace('setup.html');
    } catch (_) { /* sin backend: se queda en el login */ }
  }

  // ---------------- Enlazar formularios ----------------
  function showError(msg) {
    var el = document.getElementById('login-error') || document.getElementById('setup-error');
    if (el) { el.textContent = msg; el.classList.remove('hidden'); }
    // Fallback defensivo: este archivo es un script GLOBAL (no módulo) y NO puede
    // importar ui.js. Si alguna vista cargó el sistema de alertas en window, se
    // usa; si no, se recurre al alert() nativo como último recurso.
    else if (typeof window.mostrarAlerta === 'function') window.mostrarAlerta(msg, 'error');
    else alert(msg);
  }

  function setBusy(btn, busy, texto) {
    if (!btn) return;
    if (busy) {
      btn.dataset.original = btn.textContent;
      btn.disabled = true;
      btn.textContent = texto || 'Procesando...';
    } else {
      btn.disabled = false;
      btn.textContent = btn.dataset.original || texto;
    }
  }

  function enlazarLogin() {
    var form = document.getElementById('login-form');
    if (!form) return;
    form.addEventListener('submit', async function (e) {
      e.preventDefault();
      var btn = form.querySelector('button[type="submit"]');
      var email = (document.getElementById('login-email') || {}).value || '';
      var password = (document.getElementById('login-password') || {}).value || '';

      var errEl = document.getElementById('login-error');
      if (errEl) errEl.classList.add('hidden');
      if (!email || !password) return showError('Ingresa tu correo y contraseña');

      setBusy(btn, true, 'Ingresando...');
      try {
        var perfil = await login(email.trim(), password);
        // Inicio según rol: admin → Reportes; cajero → Punto de Venta.
        window.location.href = pantallaInicio(perfil && perfil.rol);
      } catch (err) {
        showError(err.message || 'No se pudo iniciar sesión');
        setBusy(btn, false, 'Iniciar Sesión');
      }
    });
  }

  // Scripts al final de <body>: DOM listo; enlazar ya (idempotente por elemento).
  function enlazar() {
    enlazarLogin();
    if (document.getElementById('login-form')) irAlAsistenteSiHaceFalta();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', enlazar);
  else enlazar();

  // API global
  window.authAPI = {
    getToken: getToken,
    setToken: setToken,
    clearSession: clearSession,
    fetchProfile: fetchProfile,
    login: login,
    logout: logout,
  };
  window.loginEmail = loginEmail;
  window.logout = logout;
})();
