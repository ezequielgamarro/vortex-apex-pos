/**
 * theme.js — Gestión del tema claro/oscuro (dark mode) del Punto de Venta.
 *
 * Script GLOBAL (no módulo), cargado en el <head> de TODAS las vistas,
 * ANTES de cualquier otro recurso visual, para evitar el "flash" blanco
 * (FOUC): aplica la clase `dark` sobre <html> antes del primer render.
 *
 * Diseño:
 *   1. IIFE auto-ejecutable que resuelve y aplica el tema INMEDIATAMENTE
 *      (síncrono, en el <head>). Es la pieza anti-parpadeo.
 *   2. Expone `window.theme` con la API pública para alternar el tema y
 *      consultar el estado actual (usada por el toggle del header).
 *
 * Fuente de verdad de la preferencia: localStorage['theme'].
 *   - 'dark'  -> forzar oscuro.
 *   - 'light' -> forzar claro.
 *   - (ausente/otro) -> seguir el sistema (prefers-color-scheme).
 *
 * Sin dependencias externas: vanilla JS, compatible con el resto del stack.
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'theme';        // 'dark' | 'light'
  var DARK_CLASS = 'dark';
  var root = document.documentElement;

  /** Lee la preferencia guardada ('dark' | 'light' | null). */
  function preferenciaGuardada() {
    try {
      var v = localStorage.getItem(STORAGE_KEY);
      return (v === 'dark' || v === 'light') ? v : null;
    } catch (e) {
      return null; // localStorage no disponible (modo privado, etc.)
    }
  }

  /** ¿El sistema prefiere oscuro? (fallback cuando no hay preferencia). */
  function sistemaPrefiereOscuro() {
    try {
      return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    } catch (e) {
      return false;
    }
  }

  /** Resuelve el tema efectivo: preferencia del usuario o, si no hay, el sistema. */
  function temaEfectivo() {
    return preferenciaGuardada() || (sistemaPrefiereOscuro() ? 'dark' : 'light');
  }

  /** Aplica el tema al <html> (add/remove de la clase `dark`). */
  function aplicar(tema) {
    if (tema === 'dark') {
      root.classList.add(DARK_CLASS);
    } else {
      root.classList.remove(DARK_CLASS);
    }
    // Reflejar el estado en el atributo data-theme (útil para CSS/debug).
    root.setAttribute('data-theme', tema);
  }

  /** Persiste la preferencia (best-effort: no rompe si localStorage falla). */
  function guardar(tema) {
    try { localStorage.setItem(STORAGE_KEY, tema); } catch (e) { /* noop */ }
  }

  // --------------------------------------------------------------
  // 1) APLICACIÓN INMEDIATA (anti-FOUC). Se ejecuta ya, en el <head>.
  // --------------------------------------------------------------
  aplicar(temaEfectivo());

  // --------------------------------------------------------------
  // 2) API PÚBLICA para el toggle del header (guard.js).
  // --------------------------------------------------------------
  window.theme = {
    /** Devuelve 'dark' | 'light' según el estado actual del DOM. */
    actual: function () {
      return root.classList.contains(DARK_CLASS) ? 'dark' : 'light';
    },

    /** Alterna el tema, lo aplica y lo persiste. Devuelve el nuevo tema. */
    toggle: function () {
      var nuevo = this.actual() === 'dark' ? 'light' : 'dark';
      aplicar(nuevo);
      guardar(nuevo); // a partir de aquí, la elección del usuario manda
      return nuevo;
    },

    /** Fija un tema explícito ('dark' | 'light') y lo persiste. */
    set: function (tema) {
      var t = tema === 'dark' ? 'dark' : 'light';
      aplicar(t);
      guardar(t);
      return t;
    },
  };

  // --------------------------------------------------------------
  // 3) Si NO hay preferencia guardada, seguir los cambios del sistema
  //    en vivo (el usuario aún no eligió manualmente).
  // --------------------------------------------------------------
  try {
    if (window.matchMedia) {
      var mq = window.matchMedia('(prefers-color-scheme: dark)');
      var onCambio = function (e) {
        if (!preferenciaGuardada()) aplicar(e.matches ? 'dark' : 'light');
      };
      if (mq.addEventListener) mq.addEventListener('change', onCambio);
      else if (mq.addListener) mq.addListener(onCambio); // navegadores antiguos
    }
  } catch (e) { /* noop */ }
})();
