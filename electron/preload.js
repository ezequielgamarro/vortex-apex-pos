/**
 * preload.js — Puente seguro entre el renderer web y el proceso principal.
 *
 * Se ejecuta en el contexto del renderer (cargado desde http://127.0.0.1:8000),
 * con `contextIsolation` habilitado. Expone SOLO una superficie mínima y
 * explícita al frontend (nada de Node/Electron crudo), describiendo el estado
 * del backend embebido e IPC para peticiones controladas del lado principal.
 *
 * No se altera ningún flujo previo: se agrega únicamente `window.posApp` para
 * que la UI (si lo desea) pueda consultar si el servidor embebido está listo o
 * pedir el cierre/creación del backend sin tocar Node directamente.
 */
const { contextBridge, ipcRenderer } = require('electron');

const VALID_REQUEST_CHANNELS = [
  'backend:status',
  'backend:stop',
  'backend:restart',
];

contextBridge.exposeInMainWorld('posApp', {
  // Estado actual del backend embebido.
  getBackendStatus: () => ipcRenderer.invoke('backend:get-status'),

  // Escucha pasiva para cuando el servidor queda listo/listo de nuevo.
  onBackendReady: (callback) => {
    const listener = (_event, sent) => {
      if (sent && typeof sent === 'object') callback(sent);
    };
    ipcRenderer.on('backend:ready', listener);
    return () => ipcRenderer.removeListener('backend:ready', listener);
  },

  // Solicitudes del renderer acotadas a canales permitidos.
  send: (channel, ...args) => {
    if (!VALID_REQUEST_CHANNELS.includes(channel)) {
      return Promise.reject(new Error('Canal no permitido'));
    }
    return ipcRenderer.invoke(channel, ...args);
  },
});
