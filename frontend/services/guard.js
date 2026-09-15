/**
 * guard.js — Guardia de rutas y seguridad del frontend (backend local JWT).
 *
 * Script GLOBAL auto-ejecutable. Cargar en cada vista protegida
 * (pos.html, inventario.html, caja.html) DESPUÉS de:
 *   <script src="./services/config.js"></script>
 *
 * RBAC / control de acceso por rol:
 * El rol autoritativo se extrae del **claim `rol` del JWT** guardado en
 * localStorage (clave "token", la misma que usa auth.js y api.js). Este claim
 * es determinista y no depende de la red. En paralelo se consulta `/auth/perfil`
 * sólo para datos de visualización (nombre/email) y como fuente secundaria de rol.
 *
 * Reglas:
 *   - Sin token         → redirige a login.html.
 *   - inventario.html   → visible para CUALQUIER usuario logueado (cajero lo ve
 *     en solo-lectura; crear/editar/eliminar quedan restringidas al admin en
 *     inventario.js y en el backend). Así un cajero ya no es echado al POS.
 *   - usuarios.html     → gestión de usuarios y roles (SOLO admin).
 *   - Sin rol resuelto  → NO se asume 'cajero' a ciegas: se conserva el rol
 *     cacheado en localStorage, evitando degradar a un admin por un fallo
 *     puntual de red o de decodificación.
 *
 * Nota: en esta versión ya no existe la vista dashboard.html.
 *
 * Expone `window.authGuardReady` (promesa) para que los módulos de las vistas
 * esperen a que la resolución termine antes de inicializarse.
 */
(function () {
  'use strict';

        // Rutas que exigen ser 'admin' para entrar (gestión de usuarios + reportes
    // + configuración del negocio).
  var RUTAS_SOLO_ADMIN = /(usuarios|reportes|configuracion)\.html$/;
  var TOKEN_KEY = 'token';   // clave del JWT (auth.js / api.js)
  var USER_KEY = 'user';
  var ROLE_KEY = 'rol';      // cache local del rol

  function apiBase() {
    return window.API_BASE_URL || 'http://127.0.0.1:8000/api';
  }

  function forceLogout() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(ROLE_KEY);
    if (window.location.pathname.indexOf('login.html') === -1) {
      window.location.replace('login.html');
    }
  }

  /**
   * Decodifica (sin validar firma) el payload de un JWT almacenado.
   * La parte 2 es base64url del JSON { sub, rol, exp }.
   * Devuelve el objeto de claims, o {} si no puede decodificarse.
   */
  function decodificarToken(token) {
    if (!token) return {};
    try {
      var segmentos = token.split('.');
      if (segmentos.length !== 3) return {};
      var payload = segmentos[1].replace(/-/g, '+').replace(/_/g, '/');
      while (payload.length % 4 !== 0) payload += '='; // padding base64
      var json = decodeURIComponent(
        atob(payload)
          .split('')
          .map(function (c) { return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2); })
          .join('')
      );
      return JSON.parse(json) || {};
    } catch (e) {
      console.warn('[guard.js] No se pudo decodificar el payload del token:', e.message);
      return {};
    }
  }

  // Inyecta en el Header nombre_completo y rol (badge).
  function injectHeader(perfil) {
    if (!perfil) return;
    var nombre = perfil.nombre_completo || perfil.nombre || 'Usuario';

    var nameEl = document.getElementById('profile-name');
    var initialEl = document.getElementById('profile-initial');
    var rolBadge = document.getElementById('profile-rol');

    if (nameEl) nameEl.textContent = nombre;
    if (initialEl) initialEl.textContent = nombre.charAt(0).toUpperCase();
    if (rolBadge) {
      var esAdmin = perfil.rol === 'admin';
      rolBadge.textContent = esAdmin ? 'Admin' : 'Cajero';
      rolBadge.className =
        'ml-2 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ' +
        (esAdmin ? 'bg-pos-primary text-pos-primary-text' : 'bg-pos-secondary text-pos-text-head');
    }
  }

              // Inyecta el conmutador de tema (luna/sol) en el Header.
  // Se inserta ANTES del botón de perfil (que está marcado con .ml-auto),
  // de modo que quede pegado a la derecha junto a la info de usuario.
  // Idempotente (data-theme-toggle) para no duplicarlo.
  function injectThemeToggle() {
    var header = document.querySelector('header');
    if (!header) return;
    if (header.querySelector('[data-theme-toggle]')) return;
    if (!window.theme) return; // theme.js no cargado (defensivo)

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.dataset.themeToggle = '1';
    btn.setAttribute('aria-label', 'Cambiar tema claro/oscuro');
    btn.title = 'Cambiar tema';
    // El botón se coloca justo antes del primer elemento con .ml-auto (perfil).
    btn.className =
      'p-2 rounded-lg text-pos-text-body hover:bg-pos-secondary/40 transition-colors';

    // Dos iconos: luna (en claro -> ofrece oscuro) y sol (en oscuro -> ofrece claro).
    // Se alternan por CSS vía la clase `dark` en <html> (sin JS de re-render).
    btn.innerHTML =
      // Icono LUNA: visible en tema claro.
      '<svg class="h-5 w-5 dark:hidden" fill="none" viewBox="0 0 24 24" stroke="currentColor">' +
      '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" ' +
      'd="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>' +
      // Icono SOL: visible en tema oscuro.
      '<svg class="h-5 w-5 hidden dark:block" fill="none" viewBox="0 0 24 24" stroke="currentColor">' +
      '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" ' +
      'd="M12 3v2m0 14v2m9-9h-2M5 12H3m15.36 6.36l-1.42-1.42M7.05 7.05L5.64 5.64' +
      'm12.72 0l-1.41 1.41M7.05 16.95l-1.41 1.41M16 12a4 4 0 11-8 0 4 4 0 018 0z"/></svg>';

    btn.addEventListener('click', function () {
      window.theme.toggle();
    });

        // Insertar antes del botón de perfil (primer hijo con .ml-auto) o al final.
    var perfilBtn = header.querySelector('.ml-auto');
    if (perfilBtn && perfilBtn.parentNode === header) {
      header.insertBefore(btn, perfilBtn);
    } else {
      header.appendChild(btn);
    }
  }

  // Inyecta el acceso a CONFIGURACIÓN en el Header (ícono de tuerca).
  // SOLO para rol 'admin': la configuración del negocio es una decisión
  // administrativa. Se ubica junto al conmutador de tema/perfil (a la derecha),
  // NO en el sidebar de navegación diaria. Idempotente (data-config-toggle).
  function injectConfigToggle(perfil) {
    var header = document.querySelector('header');
    if (!header) return;
    if (header.querySelector('[data-config-toggle]')) return;
    if (!perfil || perfil.rol !== 'admin') return; // RBAC: solo admin

    var a = document.createElement('a');
    a.href = 'configuracion.html';
    a.dataset.configToggle = '1';
    a.setAttribute('aria-label', 'Configuración');
    a.title = 'Configuración';
    a.className =
      'p-2 rounded-lg text-pos-text-body hover:bg-pos-secondary/40 transition-colors';
    // Icono de ENGRANAJE/TUERCA (heroicons "cog"): metáfora universal de ajustes.
    a.innerHTML =
      '<svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">' +
      '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" ' +
      'd="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/></svg>';

    // Insertar antes del botón de perfil (primer hijo con .ml-auto) o al final.
    var perfilBtn = header.querySelector('.ml-auto');
    if (perfilBtn && perfilBtn.parentNode === header) {
      header.insertBefore(a, perfilBtn);
    } else {
      header.appendChild(a);
    }
  }

  // Vincula el botón de cierre de sesión (#logout-btn). Idempotente: no
  // re-enlaza el mismo handler si renderSidebar se ejecutara más de una vez.
  function bindLogout() {
    var btn = document.getElementById('logout-btn');
    if (!btn) return;
    if (btn.dataset.logoutBound === '1') return;
    btn.dataset.logoutBound = '1';
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      forceLogout();
    });
  }

  // ==========================================================================
  // SIDEBAR — Single Source of Truth
  // --------------------------------------------------------------------------
  // El orden ABSOLUTO del menú lateral se declara una única vez aquí (arreglo
  // MENU_ITEMS). Ninguna vista debe hardcodear enlaces en su
  // <nav id="sidebar-menu">; guard.js es el ÚNICO responsable de poblarlo vía
  // renderSidebar(). Esto elimina el reordenamiento producido por mezclar HTML
  // estático con inserciones imperativas (los antiguos injectMenu*).
  // Config-driven: agregar/mover/ocultar un ítem = editar este arreglo y se
  // propaga a TODAS las vistas por igual.
  // ==========================================================================

  // Estilos del enlace de menú (fuente única para estado normal y activo).
  var CLASE_ITEM =
    'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium ' +
    'text-pos-text-body hover:bg-pos-secondary/40 transition-colors';
  // Estilos del ítem activo: fondo gris resaltado + texto resaltado.
  var CLASE_ITEM_ACTIVO =
    'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium ' +
    'bg-pos-secondary/60 text-pos-text-head';

  // Orden absoluto del menú. `soloAdmin: true` = filtrado RBAC declarativo.
  // `primero: true` = el ítem se antepone a los demás (tras el filtrado RBAC).
  //   Ej.: Reportes es la pantalla de inicio del admin, por eso va arriba.
  //   Para el cajero (que no ve Reportes) el primer ítem sigue siendo POS.
  var MENU_ITEMS = [
        { id: 'pos',             href: 'pos.html',             label: 'Punto de Venta' },
    { id: 'ventas',          href: 'ventas.html',          label: 'Ventas' },
    { id: 'inventario',      href: 'inventario.html',      label: 'Inventario' },
    { id: 'caja',            href: 'caja.html',            label: 'Control de Caja' },
    { id: 'historial-cajas', href: 'historial-cajas.html', label: 'Historial de Cajas', badge: { texto: 'Cerradas', clase: 'badge badge-neutral' } },
    { id: 'reportes',        href: 'reportes.html',        label: 'Reportes', soloAdmin: true, primero: true },
    { id: 'cuentas',         href: 'cuentas.html',         label: 'Cuentas Corrientes' },
    { id: 'usuarios',        href: 'usuarios.html',        label: 'Usuarios', soloAdmin: true, badge: { texto: 'Admin', clase: 'badge badge-primary' } },
  ];

  // Basename de la ruta actual, robusto ante subcarpetas:
  // '/x/y/pos.html' -> 'pos.html'.
  function archivoActual() {
    var partes = window.location.pathname.split('/');
    return partes[partes.length - 1] || '';
  }

  // Renderiza el sidebar completo dentro de <nav id="sidebar-menu">.
  // Idempotente: vacía el contenedor antes de inyectar (sin duplicados).
  function renderSidebar(perfil) {
    var nav = document.getElementById('sidebar-menu');
    if (!nav) return;

    var esAdmin = !!perfil && perfil.rol === 'admin';
    var actual = archivoActual();

    nav.innerHTML = ''; // SSOT: reconstruir desde datos, nunca parchear el DOM.

    // Sección "Principal".
    var tituloPrincipal = document.createElement('p');
    tituloPrincipal.className =
      'px-3 text-xs font-semibold text-pos-text-body/60 uppercase tracking-wider mb-2';
    tituloPrincipal.textContent = 'Principal';
    nav.appendChild(tituloPrincipal);

        // 1) Filtrar por RBAC y 2) anteponer los ítems marcados con `primero`.
    // El orden del arreglo MENU_ITEMS se conserva como base (sort estable),
    // de modo que mover/agregar ítems siga siendo predecible.
    var visibles = MENU_ITEMS.filter(function (item) {
      return !(item.soloAdmin && !esAdmin);
    });
    var priorizados = visibles.filter(function (item) { return item.primero; });
    var resto = visibles.filter(function (item) { return !item.primero; });
    var ordenados = priorizados.concat(resto);

    ordenados.forEach(function (item) {
      var a = document.createElement('a');
      a.href = item.href;
      a.dataset.menu = item.id;
      // Ítem activo = comparación del href con la ruta actual (basename).
      a.className = (item.href === actual) ? CLASE_ITEM_ACTIVO : CLASE_ITEM;

      var span = document.createElement('span');
      span.textContent = item.label;
      a.appendChild(span);

      if (item.badge) {
        var badge = document.createElement('span');
        badge.className = 'ml-auto text-xs ' + item.badge.clase;
        badge.textContent = item.badge.texto;
        a.appendChild(badge);
      }

      nav.appendChild(a);
    });

    // Sección "Sesión" (siempre al final, tras los ítems de navegación).
    var tituloSesion = document.createElement('p');
    tituloSesion.className =
      'px-3 text-xs font-semibold text-pos-text-body/60 uppercase tracking-wider mt-6 mb-2';
    tituloSesion.textContent = 'Sesión';
    nav.appendChild(tituloSesion);

    // Botón de cierre de sesión: se recrea en cada render. Por eso el evento
    // DEBE rehacerse con bindLogout() justo después de llamar a renderSidebar().
    var logout = document.createElement('a');
    logout.href = 'login.html';
    logout.id = 'logout-btn';
    logout.className =
      'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium ' +
      'text-pos-danger hover:bg-pos-danger/10 transition-colors';
    var spanLogout = document.createElement('span');
    spanLogout.textContent = 'Cerrar sesión';
    logout.appendChild(spanLogout);
    nav.appendChild(logout);
  }

  // ---------- Boot de la guardia ----------
  window.addEventListener('licencia-vencida', function (e) {
    if (window.location.pathname.indexOf('bloqueo.html') === -1) {
      window.location.replace('bloqueo.html');
    }
  });

  var resolveReady;
  window.authGuardReady = new Promise(function (resolve) { resolveReady = resolve; });

  var token = localStorage.getItem(TOKEN_KEY);

  // 1) Sin token → login.
  if (!token) {
    forceLogout();
    return; // la promesa nunca resuelve; la vista no continúa
  }

  // 2) Autoridad de rol: claim del JWT (determinista y sin red).
  var claims = decodificarToken(token);
  var rol = claims.rol;        // 'admin' | 'cajero' | undefined
  var perfil = null;           // perfil servido por /auth/perfil (display)

  (async function boot() {
    // /perfil para datos de visualización y, si el JWT no trajo rol, como
    // fuente secundaria (el backend refleja el rol actual del usuario).
    try {
      var res = await fetch(apiBase() + '/auth/perfil', {
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + token,
        },
      });
      if (res.status === 401 || res.status === 403) {
        forceLogout();
        return;
      }
      if (res.ok) {
        perfil = await res.json();
        rol = rol || perfil.rol || localStorage.getItem(ROLE_KEY);
      }
    } catch (err) {
      // Backend inalcanzable: conservar el rol del JWT / cache (sin degradar).
      console.warn('[guard.js] No se pudo validar la sesión en el backend:', err.message);
    }

    // Falla total de ambas fuentes: último recurso = rol cacheado.
    if (!rol) rol = localStorage.getItem(ROLE_KEY);

        // Normalización del perfil para visualización.
    // Se preserva `rubro` (multi-rubro): si no viene de /perfil, se recupera
    // del cache local o del perfil de fallback para no perder el contexto.
    var cachePrev = null;
    try { cachePrev = JSON.parse(localStorage.getItem(USER_KEY) || 'null'); } catch (_) {}
    if (!perfil) {
      perfil = {
        id: claims.sub || (cachePrev && cachePrev.id) || null,
        nombre: (cachePrev && cachePrev.nombre) || claims.email || 'Usuario',
        rol: rol || 'cajero',
        rubro: (cachePrev && cachePrev.rubro) || 'general',
      };
    }
    // Garantizar que `rubro` siempre exista en el perfil persistido.
    if (!perfil.rubro) {
      perfil.rubro = (cachePrev && cachePrev.rubro) || 'general';
    }

    // Almacenar (norma local) rol + perfil (incluye rubro) para el resto de la app.
    localStorage.setItem(ROLE_KEY, rol || 'cajero');
    localStorage.setItem(USER_KEY, JSON.stringify(perfil));

    // Hidratar el NOMBRE DEL NEGOCIO en window para que los tickets (POS y
    // cierre de caja) lo impriman sin consultar la API por su cuenta. Es un
    // dato de configuración global; si la consulta falla, se conserva el valor
    // previo (o vacío) y la impresión no se rompe.
    try {
      var cfgRes = await fetch(apiBase() + '/configuracion', {
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + token,
        },
      });
      if (cfgRes.ok) {
        var cfg = await cfgRes.json();
        if (cfg && typeof cfg.nombre === 'string') {
          window.NEGOCIO_NOMBRE = cfg.nombre;
        }
      }
    } catch (cfgErr) {
      console.warn('[guard.js] No se pudo cargar el nombre del negocio:', cfgErr.message);
    }

    // 3) Control de acceso por rol.
    //    - inventario.html: acceso libre (cualquier usuario logueado). El detalle
    //      de crear/editar/eliminar lo restringe la propia vista (rol === 'admin').
    //    - usuarios.html: SOLO el rol 'admin'.
    //    Por seguridad, a quienes no son admin se les oculta además el enlace
    //    "Usuarios" del sidebar (propiedad oculta-set por la vista).
    if (RUTAS_SOLO_ADMIN.test(window.location.pathname) && rol !== 'admin') {
      // Custodiar el rol: un no-admin nunca debe ver la gestión de usuarios.
      window.location.replace('pos.html');
      return;
    }

    // 3.5) Banner proactivo de licencia (por_vencer o gracia)
    try {
      var licRes = await fetch(apiBase() + '/licencia/estado', {
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + token,
        },
      });
      if (licRes.ok) {
        var lic = await licRes.json();
        if (lic.estado === 'por_vencer' || lic.estado === 'gracia') {
          var mainEl = document.querySelector('main');
          if (mainEl) {
            var isGracia = lic.estado === 'gracia';
            var banner = document.createElement('div');
            banner.className = 'w-full p-3 mb-4 rounded-lg flex items-center justify-between text-sm shadow-sm ' + 
              (isGracia ? 'bg-pos-danger/10 border border-pos-danger text-pos-danger' : 'bg-yellow-500/10 border border-yellow-500 text-yellow-600 dark:text-yellow-400');
            
            var msg = isGracia 
              ? `<b>Atención:</b> Tu licencia está vencida (período de gracia). Se bloqueará en ${lic.dias_restantes} día(s).`
              : `<b>Aviso:</b> Tu licencia vencerá en ${lic.dias_restantes} día(s).`;
            
            banner.innerHTML = `
              <div class="flex items-center gap-2">
                <svg class="h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
                <span>${msg}</span>
              </div>
              <button class="shrink-0 p-1 opacity-70 hover:opacity-100" onclick="this.parentElement.remove()" aria-label="Cerrar">
                <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
              </button>
            `;
            // Insert at the top of main
            mainEl.insertBefore(banner, mainEl.firstChild);
          }
        }
      }
    } catch (e) {
      console.warn('[guard.js] No se pudo obtener estado de licencia:', e.message);
    }

    // 4) Header + render del sidebar (Single Source of Truth) + 5) re-enlace
    //    del logout.
    injectHeader(perfil);
    injectThemeToggle();
    injectConfigToggle(perfil);
    renderSidebar(perfil);
    // CRÍTICO: renderSidebar recrea #logout-btn, por lo que bindLogout() debe
    // ejecutarse DESPUÉS del render para que el botón quede funcional.
    bindLogout();

    resolveReady(perfil);
  })();
})();
