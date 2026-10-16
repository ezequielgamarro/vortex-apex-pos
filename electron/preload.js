/**
 * preload.js — Puente seguro entre el renderer web y el proceso principal.
 *
 * Se ejecuta en el contexto del renderer (cargado desde http://127.0.0.1:8000),
 * con `contextIsolation` habilitado. Expone SOLO una superficie mínima y de
 * lectura (nada de Node/Electron crudo): el estado del backend embebido y el
 * aviso de que quedó listo.
 *
 * Detener o reiniciar el backend NO se expone a propósito: la interfaz no lo
 * necesita y una página comprometida podría usarlo para tumbar el POS.
 */
const { contextBridge, ipcRenderer } = require('electron');

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
});
