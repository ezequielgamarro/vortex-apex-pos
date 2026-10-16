/**
 * recuperar.js — Recuperación de contraseña con un código firmado por el proveedor.
 *
 * Script GLOBAL cargado en `recuperar.html` DESPUÉS de `config.js`.
 *   GET  /setup/huella     -> huella de esta PC (se la envía al proveedor).
 *   POST /setup/recuperar  -> {codigo, email, password}: pone la contraseña nueva.
 * Al terminar vuelve al login. Sin código válido no se cambia nada.
 */
(function () {
  'use strict';

  var form = document.getElementById('recuperar-form');
  if (!form) return;

  function apiBase() {
    return window.API_BASE_URL || 'http://127.0.0.1:8000/api';
  }
  function val(id) {
    var el = document.getElementById(id);
    return el ? el.value : '';
  }
  function mostrar(id, msg) {
    var el = document.getElementById(id);
    if (!el) return;
    el.textContent = msg; // textContent: nunca interpreta HTML
    el.classList.remove('hidden');
  }
  function ocultar(id) {
    var el = document.getElementById(id);
    if (el) el.classList.add('hidden');
  }

  async function cargarHuella() {
    try {
      var res = await fetch(apiBase() + '/setup/huella');
      var data = await res.json();
      var el = document.getElementById('rec-huella');
      if (el) {
        el.value = data.huella || '';
        el.addEventListener('focus', function () { el.select(); });
      }
    } catch (_) {
      mostrar('rec-error', 'No se pudo conectar con el programa. Reinícialo e intenta de nuevo.');
    }
  }

  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    ocultar('rec-error');
    ocultar('rec-ok');

    var codigo = val('rec-codigo').trim();
    var email = val('rec-email').trim();
    var password = val('rec-password');

    if (!codigo) return mostrar('rec-error', 'Ingresa el código de recuperación.');
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      return mostrar('rec-error', 'Ingresa un correo electrónico válido.');
    }
    if (password.length < 8) {
      return mostrar('rec-error', 'La contraseña debe tener al menos 8 caracteres.');
    }
    if (password !== val('rec-password2')) {
      return mostrar('rec-error', 'Las contraseñas no coinciden.');
    }

    var btn = form.querySelector('button[type="submit"]');
    btn.disabled = true;
    var textoOriginal = btn.textContent;
    btn.textContent = 'Cambiando...';
    try {
      var res = await fetch(apiBase() + '/setup/recuperar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ codigo: codigo, email: email, password: password }),
      });
      var data = null;
      try { data = await res.json(); } catch (_) { /* cuerpo vacío */ }
      if (!res.ok) {
        throw new Error(data && typeof data.detail === 'string'
          ? data.detail
          : 'Revisa los datos ingresados.');
      }
      mostrar('rec-ok', 'Listo: contraseña cambiada. Te llevamos al inicio de sesión…');
      setTimeout(function () { window.location.href = 'login.html'; }, 1800);
    } catch (err) {
      mostrar('rec-error', err.message || 'No se pudo cambiar la contraseña.');
      btn.disabled = false;
      btn.textContent = textoOriginal;
    }
  });

  cargarHuella();
})();
