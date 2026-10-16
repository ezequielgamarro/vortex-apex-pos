/**
 * setup.js — Asistente de primer arranque (alta del primer administrador).
 *
 * Script GLOBAL cargado en `setup.html` DESPUÉS de `config.js` y `auth.js`.
 * Habla con el backend local:
 *   GET  /setup/estado       -> ¿la instalación está vacía? + huella de la PC.
 *   POST /setup/inicializar  -> crea el admin con un código de alta firmado.
 * Si la instalación ya tiene usuarios, vuelve al login.
 */
(function () {
  'use strict';

  var form = document.getElementById('setup-form');
  if (!form) return;

  function apiBase() {
    return window.API_BASE_URL || 'http://127.0.0.1:8000/api';
  }

  function val(id) {
    var el = document.getElementById(id);
    return el ? el.value : '';
  }

  function mostrarError(msg) {
    var el = document.getElementById('setup-error');
    if (!el) return;
    el.textContent = msg; // textContent: nunca interpreta HTML
    el.classList.remove('hidden');
  }

  function ocultarError() {
    var el = document.getElementById('setup-error');
    if (el) el.classList.add('hidden');
  }

  function setBusy(btn, busy, texto) {
    if (!btn) return;
    if (busy) {
      btn.dataset.original = btn.textContent;
      btn.disabled = true;
      btn.textContent = texto;
    } else {
      btn.disabled = false;
      btn.textContent = btn.dataset.original || texto;
    }
  }

  async function cargarEstado() {
    try {
      var res = await fetch(apiBase() + '/setup/estado');
      var estado = await res.json();
      if (!estado.necesita_setup) {
        window.location.replace('login.html');
        return;
      }
      var huellaEl = document.getElementById('setup-huella');
      if (huellaEl) {
        huellaEl.value = estado.huella || '';
        huellaEl.addEventListener('focus', function () { huellaEl.select(); });
      }
    } catch (_) {
      mostrarError('No se pudo conectar con el programa. Reinícialo e intenta de nuevo.');
    }
  }

  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    ocultarError();

    var codigo = val('setup-codigo').trim();
    var nombre = val('setup-nombre').trim();
    var email = val('setup-email').trim();
    var password = val('setup-password');

    if (!codigo) return mostrarError('Ingresa el código de alta.');
    if (!nombre) return mostrarError('Ingresa tu nombre.');
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      return mostrarError('Ingresa un correo electrónico válido.');
    }
    if (password.length < 8) {
      return mostrarError('La contraseña debe tener al menos 8 caracteres.');
    }
    if (password !== val('setup-password2')) {
      return mostrarError('Las contraseñas no coinciden.');
    }

    var btn = form.querySelector('button[type="submit"]');
    setBusy(btn, true, 'Creando...');
    try {
      var res = await fetch(apiBase() + '/setup/inicializar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          codigo_alta: codigo,
          nombre: nombre,
          email: email,
          password: password,
        }),
      });
      var data = null;
      try { data = await res.json(); } catch (_) { /* cuerpo vacío */ }

      if (!res.ok) {
        var detalle = data && typeof data.detail === 'string'
          ? data.detail
          : 'Revisa los datos ingresados.';
        throw new Error(detalle);
      }
      if (!data || !data.access_token) {
        throw new Error('El servidor no devolvió un token de acceso.');
      }
      window.authAPI.setToken(data.access_token);
      await window.authAPI.fetchProfile();
      window.location.href = 'reportes.html';
    } catch (err) {
      mostrarError(err.message || 'No se pudo crear el administrador.');
      setBusy(btn, false, 'Crear administrador');
    }
  });

  cargarEstado();
})();
