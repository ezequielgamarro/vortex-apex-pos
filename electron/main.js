/**
 * main.js — Proceso principal de la aplicación de escritorio (Electron).
 *
 * Responsabilidades:
 *  1. Lanzar en segundo plano el backend embebido `pos-backend.exe`
 *     (FastAPI + SQLite) con child_process.spawn.
 *  2. Cargar la interfaz que el propio backend sirve de forma estática
 *     (http://127.0.0.1:8000/login.html). Así se conserva 1:1 el flujo actual:
 *     misma origin para la UI y para las llamadas /api del frontend
 *     (config.js usa API_BASE_URL = http://127.0.0.1:8000/api).
 *  3. Garantizar que al cerrar la app el proceso backend se destruya (sin
 *     huérfanos ni hijacked ports), y ofrecer IPC controlado al renderer.
 *
 * Convivencia con el backend:
 *  `dist/pos-backend.exe` es un one-file PyInstaller de `app/server.py`, que
 *  eleva su propio uvicorn (import string "app.main:app") en 127.0.0.1:8000.
 *  Este proceso principal SOLO lo lanza, espera a que /health responda y, una
 *  vez saludable, navega la ventana a http://127.0.0.1:8000/login.html. La
 *  UI nunca se carga antes de que el backend esté listo (evita la pantalla
 *  blanca que produce cargar un puerto todavía apagado).
 */
const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');
const fs = require('fs');

// ------------------------------------------------------------------
// Log a archivo (diagnóstico). Escribe en userData/main-debug.log.
// Captura la secuencia de arranque para ver dónde se detiene la app.
// ------------------------------------------------------------------
let DEBUG_LOG_PATH = null;
const DEBUG_LOG_MAX_BYTES = 1024 * 1024; // 1 MB: al superarlo se rota (queda 1 copia)
function dlog(...args) {
  try {
    const linea = `[${new Date().toISOString()}] ${args.join(' ')}\n`;
    if (!DEBUG_LOG_PATH) {
      try { DEBUG_LOG_PATH = path.join(app.getPath('userData'), 'main-debug.log'); } catch { DEBUG_LOG_PATH = null; }
    }
    if (DEBUG_LOG_PATH) {
      try {
        if (fs.statSync(DEBUG_LOG_PATH).size > DEBUG_LOG_MAX_BYTES) {
          fs.renameSync(DEBUG_LOG_PATH, `${DEBUG_LOG_PATH}.old`);
        }
      } catch { /* el archivo aún no existe */ }
      fs.appendFileSync(DEBUG_LOG_PATH, linea);
    }
    console.log('[main]', ...args);
  } catch (_) { /* nunca romper por logging */ }
}
process.on('uncaughtException', (e) => dlog('UNCAUGHT EXCEPTION:', e && e.stack ? e.stack : String(e)));
process.on('unhandledRejection', (e) => dlog('UNHANDLED REJECTION:', e && e.stack ? e.stack : String(e)));
dlog('=== app arrancando ===');

// ------------------------------------------------------------------
// Configuración (override vía entorno permite tests/CI)
// ------------------------------------------------------------------
// El backend SOLO puede escuchar en esta PC: un POS no debe quedar expuesto a la
// red local por una variable de entorno olvidada. Cualquier otro host se ignora.
const HOSTS_PERMITIDOS = ['127.0.0.1', 'localhost'];
const BACKEND_HOST = HOSTS_PERMITIDOS.includes(process.env.POS_BACKEND_HOST)
  ? process.env.POS_BACKEND_HOST
  : '127.0.0.1';
if (process.env.POS_BACKEND_HOST && process.env.POS_BACKEND_HOST !== BACKEND_HOST) {
  dlog('POS_BACKEND_HOST ignorado (solo loopback permitido):', process.env.POS_BACKEND_HOST);
}
const BACKEND_PORT = Number(process.env.POS_BACKEND_PORT || 8000);
const BACKEND_BASE_URL = `http://${BACKEND_HOST}:${BACKEND_PORT}`;
const BACKEND_ORIGIN = new URL(BACKEND_BASE_URL).origin;
const HEALTH_URL = `${BACKEND_BASE_URL}/health`;

/**
 * ¿La URL pertenece al origen de la app? Compara el ORIGEN ya parseado: un
 * `startsWith` aceptaría `http://127.0.0.1:8000.evil.com` o `...:80001`.
 */
function esUrlPropia(url) {
  try {
    return new URL(url).origin === BACKEND_ORIGIN;
  } catch {
    return false;
  }
}

/** Escapa texto para insertarlo en HTML (mensajes de error que se muestran). */
function escHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

// En desarrollo apunta a dist/pos-backend.exe en la raíz; en el instalador el
// ejecutable vive en process.resourcesPath (extraResources) junto a la app.
function resolveBackendPath() {
  if (app.isPackaged) {
    const p = path.join(process.resourcesPath, 'pos-backend.exe');
    dlog('resolveBackendPath (packaged):', p, 'existe:', fs.existsSync(p));
    return p;
  }
  // Modo desarrollo: la exe se genera en `dist/pos-backend.exe` (PyInstaller).
  const p = path.join(app.getAppPath(), 'dist', 'pos-backend.exe');
  dlog('resolveBackendPath (dev):', p, 'existe:', fs.existsSync(p));
  return p;
}

// ------------------------------------------------------------------
// Estado global
// ------------------------------------------------------------------
let backendProcess = null; // child del backend spawn
let backendState = { running: false, pid: null, error: null };
let mainWindow = null;

const log = (...args) => console.log('[backend]', ...args);
const errLog = (...args) => console.error('[backend]', ...args);

// Corta el proceso (y a sus hijos, si es posible) sin dejar huérfanos en Win.
function destroyBackend() {
  if (!backendProcess || backendProcess.killed) return;

  const proc = backendProcess;
  backendProcess = null;
  backendState = { running: false, pid: null, error: null };
  log('finalizando backend (pid=%s)...', proc.pid);

  if (process.platform === 'win32') {
    // taskkill /T cierra el árbol completo (evita huérfanos de uvicorn reload)
    try {
      const taskkill = spawn(
        'taskkill',
        ['/PID', String(proc.pid), '/T', '/F'],
        { windowsHide: true }
      );
      taskkill.unref();
      return;
    } catch (e) {
      errLog('taskkill no disponible, usando kill()', e);
    }
  }
  proc.kill();
}

// Espera a que el backend responda /health (con reintentos).
// Timeout generoso: en frío el one-file PyInstaller debe extraerse y el
// lifespan (crear BD + seed del admin usando bcrypt) puede tardar >25 s.
function waitForBackend(timeoutMs = 45000, intervalMs = 800) {
  const startedAt = Date.now();
  return new Promise((resolve) => {
    const ping = () => {
      const req = http.get(HEALTH_URL, (res) => {
        res.resume(); // drena el body
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(true);
          return;
        }
        retry();
      });
      req.on('error', retry);
      req.setTimeout(2500, () => { req.destroy(); retry(); });
    };
    const retry = () => {
      if (Date.now() - startedAt > timeoutMs) {
        resolve(false);
        return;
      }
      setTimeout(ping, intervalMs);
    };
    setTimeout(ping, 100);
  });
}

async function startBackend() {
  const exePath = resolveBackendPath();
  if (!require('fs').existsSync(exePath)) {
    backendState = {
      running: false,
      pid: null,
      error: `No se encontró el backend en: ${exePath}. Genera dist/pos-backend.exe con PyInstaller.`,
    };
    errLog(backendState.error);
    showBackendError(backendState.error);
    return;
  }

  log('arrancando backend embebido: %s', exePath);
  // Ruta segura y escribible para los datos del usuario. `userData` cae en
  // %APPDATA%\<product> y es grabable incluso instalado en Program Files, a
  // diferencia de process.resourcesPath. El backend (app/database.py) usa esta
  // variable para ubicar pos_local.db; si no viene, mantiene su comportamiento.
  const userDataDir = app.getPath('userData');
  // mkdirSync con recursive crea la carpeta (si aún no existe) sin error.
  require('fs').mkdirSync(userDataDir, { recursive: true });
  const child = spawn(exePath, [], {
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
    // POS_BACKEND_HOST/PORT van explícitos y ya saneados: el backend los lee
    // directamente del entorno (app/server.py).
    env: {
      ...process.env,
      USER_DATA_DIR: userDataDir,
      POS_BACKEND_HOST: BACKEND_HOST,
      POS_BACKEND_PORT: String(BACKEND_PORT),
    },
  });

  backendProcess = child;
  backendState = { running: true, pid: child.pid, error: null };

  child.stdout.on('data', (d) => log(String(d).trim()));
  child.stderr.on('data', (d) => errLog(String(d).trim()));

  child.on('error', (e) => {
    backendState.running = false;
    backendState.error = e && e.message ? e.message : 'Error al iniciar el backend';
    errLog(backendState.error);
    showBackendError(backendState.error);
  });

  child.on('exit', (code, signal) => {
    // Solo se notifica cuando no fue un cierre intencional de la app.
    if (backendProcess === child) {
      backendProcess = null;
      backendState.running = false;
      log('backend terminó (código=%s señal=%s)', code, signal);
    }
  });

  const ready = await waitForBackend();
  if (ready) {
    backendState.running = true;
    backendState.error = null;
    log('backend saludable → ', HEALTH_URL);
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('backend:ready', { ready: true });
      // Ahora sí cargamos la UI (el servidor ya responde).
      loadAppUI();
    }
  } else {
    backendState.error = `El backend no respondió en ${BACKEND_BASE_URL}. ¿Escucha el .exe en este puerto?`;
    // destroyBackend usa taskkill /T en Windows: mata también el subproceso
    // "real" que el one-file de PyInstaller lanza tras su bootloader (si no,
    // quedaría huérfano y ocupando el puerto).
    destroyBackend();
    errLog(backendState.error);
    showBackendError(`${backendState.error}\n\nRevisa que pos-backend.exe levante uvicorn en el puerto indicado.`);
  }
}

function showBackendError(message) {
  if (mainWindow && !mainWindow.isDestroyed() && backendState.running === false) {
    mainWindow.loadURL('data:text/html;charset=utf-8,' +
      encodeURIComponent(`<html><body style="font-family:sans-serif;padding:40px">
        <h2>No se pudo iniciar el servidor local</h2>
        <pre style="white-space:pre-wrap">${escHtml(message)}</pre>
        </body></html>`));
  }
}

// ------------------------------------------------------------------
// Ventana
// ------------------------------------------------------------------
function splashHtml(title) {
  // Página de carga segura (sin red): se muestra mientras el backend arranca.
  const body = `
    <html style="background:#6246ea;color:#fffffe;margin:0;height:100%;">
    <body style="margin:0;height:100%;display:flex;align-items:center;justify-content:center;
      font-family:system-ui,sans-serif;">
      <div style="text-align:center;">
        <h2 style="margin:0 0 8px;">Punto de Venta</h2>
        <p style="opacity:.85;margin:0;">${title}</p>
      </div>
    </body></html>`;
  return `data:text/html;charset=utf-8,${encodeURIComponent(body)}`;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 640,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
    },
  });

  mainWindow.removeMenu();
  mainWindow.once('ready-to-show', () => mainWindow.show());
  mainWindow.on('closed', () => { mainWindow = null; });

  // Antes de que el backend esté listo mostramos un splash; NUNCA cargamos la
  // URL remota si el puerto aún no escucha (evita pantalla blanca de error).
  mainWindow.loadURL(splashHtml('Conectando servidor local…'));

  // Navegación restringida al origin local de la app.
  // (El splash y la pantalla de error son `data:`: los carga main con loadURL,
  // que no dispara will-navigate; solo se bloquea lo que inicie la página.)
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (!esUrlPropia(url)) event.preventDefault();
  });
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (esUrlPropia(url)) return { action: 'allow' };
    return { action: 'deny' };
  });

  // Si la primera carga remota falla (p. ej. el puerto aún arrancaba), en
  // lugar de dejar una pantalla blanca se reintenta automáticamente la UI.
  mainWindow.webContents.on('did-fail-load', (_e, errCode, desc, validatedURL) => {
    // Solo reintentamos si la URL que falló es de nuestra app y no es
    // aborted (-3, navegación normal que se cancela).
    if (validatedURL && esUrlPropia(validatedURL) && errCode === -3) return;
    if (mainWindow && !mainWindow.isDestroyed() && backendState.running) {
      errLog('carga de UI falló (%s) — reintentando login', desc);
      loadAppUI();
    }
  });
}

// Carga la UI real SOLO cuando el backend está respondiendo.
let uiLoadAttempts = 0;
async function loadAppUI() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  try {
    // Refuerzo: comprobamos /health justo antes. Si aún no, reintentamos.
    const healthy = await isBackendHealthy();
    if (!healthy) {
      if (uiLoadAttempts < 30) {
        uiLoadAttempts += 1;
        await new Promise((r) => setTimeout(r, 1000));
        return loadAppUI();
      }
      return;
    }
    await mainWindow.loadURL(`${BACKEND_BASE_URL}/login.html`);
  } catch (e) {
    errLog('loadURL falló, reintentando en 1s:', e.message);
    await new Promise((r) => setTimeout(r, 1000));
    if (mainWindow && !mainWindow.isDestroyed()) loadAppUI();
  }
}

// Comprueba en un instante que el backend responde 2xx en /health.
function isBackendHealthy() {
  return new Promise((resolve) => {
    const req = http.get(HEALTH_URL, (res) => {
      res.resume();
      resolve(res.statusCode >= 200 && res.statusCode < 300);
    });
    req.on('error', () => resolve(false));
    req.setTimeout(2000, () => { req.destroy(); resolve(false); });
  });
}

// ------------------------------------------------------------------
// IPC (control controlado desde el renderer)
// ------------------------------------------------------------------
function registerIpc() {
  // Único canal expuesto al renderer, y de SOLO LECTURA. Parar o reiniciar el
  // backend ya no se ofrece desde la página: la UI no lo usa y, si una página
  // (p. ej. con XSS) pudiera pedirlo, se podría tumbar el POS en pleno cobro.
  ipcMain.handle('backend:get-status', (event) => {
    // Solo responde a la página de la propia app (no a otros frames/orígenes).
    const url = event.senderFrame && event.senderFrame.url;
    if (!esUrlPropia(url)) {
      throw new Error('Origen no autorizado');
    }
    return { ...backendState, baseUrl: BACKEND_BASE_URL };
  });
}

// Endurecimiento global de la sesión: la app no necesita ningún permiso del
// navegador (cámara, micrófono, ubicación, notificaciones...) ni webviews.
function endurecerSesion() {
  const { session } = require('electron');
  session.defaultSession.setPermissionRequestHandler((_wc, _permiso, callback) => callback(false));
  session.defaultSession.setPermissionCheckHandler(() => false);
  app.on('web-contents-created', (_event, contents) => {
    contents.on('will-attach-webview', (e) => e.preventDefault());
  });
}

// ------------------------------------------------------------------
// Ciclo de vida
// ------------------------------------------------------------------
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    dlog('app ready. version:', app.getVersion(), 'isPackaged:', app.isPackaged);
    endurecerSesion();
    registerIpc();
    createWindow();
    await startBackend();

    // macOS: convención estándar sin perder el manejador existente si lo hubiera.
    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
  });

  app.on('window-all-closed', (event) => {
    dlog('window-all-closed -> quit');
    // Cerramos backend y abandonamos la app en cualquier SO cuando no hay ventanas.
    destroyBackend();
    if (process.platform !== 'darwin') app.quit();
  });
  app.on('render-process-gone', (_e, _wc, details) => dlog('render-process-gone:', JSON.stringify(details)));
  app.on('child-process-gone', (_e, details) => dlog('child-process-gone:', JSON.stringify(details)));

  app.on('before-quit', () => destroyBackend());
  app.on('will-quit', () => destroyBackend());
  process.on('exit', () => destroyBackend());
}
