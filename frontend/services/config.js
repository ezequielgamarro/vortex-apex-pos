/**
 * config.js — Configuración del frontend del Punto de Venta.
 *
 * Cargado como SCRIPT GLOBAL (no módulo) ANTES que `auth.js` y `guard.js`.
 * Ya NO depende de Supabase: la aplicación se conecta al backend **local**
 * FastAPI + SQLite (servido en http://127.0.0.1:8000).
 *
 * Expone en `window`:
 *   - window.API_BASE_URL   : base de la REST API (prefijo /api).
 *   - window.NEGOCIO_NOMBRE : nombre del comercio impreso en los tickets
 *                             (comprobante de venta y cierre de caja).
 */
(function () {
  'use strict';

  // ============================================================
  // URL BASE DE LA API LOCAL
  // El backend FastAPI corre en el host local de la aplicación de
  // escritorio (empacada con PyInstaller). `http://127.0.0.1:8000/api`
  // apunta a la API respetando el `API_PREFIX` configurado en el backend.
  //
  // En un entorno empaquetado, este host:puerto debe coincidir con el
  // puerto que escucha el ejecutable.
  // ============================================================
  const API_BASE_URL = 'http://127.0.0.1:8000/api';

  // ============================================================
  // NOMBRE DEL NEGOCIO (encabezado de los tickets impresos)
  // ------------------------------------------------------------
  // El valor PERSISTENTE vive en la base de datos (tabla
  // `configuracion_negocio`, editable desde Configuración → Negocio).
  // guard.js lo hidrata en `window.NEGOCIO_NOMBRE` tras autenticar, de
  // modo que TODAS las vistas (POS y cierre de caja) impriman el mismo
  // nombre sin consultar la API por su cuenta.
  //
  // Este literal es solo un valor INICIAL/fallback previo a la hidratación;
  // se sobreescribe cuando guard.js resuelve la sesión. Dejarlo vacío ('')
  // evita imprimir la marca del software si la BD no tiene nombre cargado.
  // ============================================================
  const NEGOCIO_NOMBRE = '';

  window.API_BASE_URL = API_BASE_URL;
  window.NEGOCIO_NOMBRE = window.NEGOCIO_NOMBRE || NEGOCIO_NOMBRE;
})();
