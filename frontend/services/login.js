/**
 * login.js — (legacy) Respaldo de la lógica de login.
 *
 * La autenticación activa vive en `services/auth.js`, que habla con el backend
 * local FastAPI (formato OAuth2 urlencoded) y guarda el JWT en localStorage.
 *
 * Este archivo se conserva únicamente por compatibilidad con referencias
 * antiguas; ya no carga el SDK de Supabase (fue eliminado por completo).
 */
console.warn('[login.js] Obsoleto. Usa services/auth.js para el login local.');

window['loginEmail'] = window['loginEmail'] ||
  (async function (email, password) {
    // Delegar a auth.js si está disponible
    if (window.authAPI && typeof window.authAPI.login === 'function') {
      var perfil = await window.authAPI.login(email, password);
      window.location.href = 'pos.html'; // dashboard eliminado en esta versión
      return perfil;
    }
    throw new Error('auth.js no cargado');
  });
