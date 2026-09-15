/**
 * Config TEMPORAL de electron-builder (solo para esta sesión de build).
 * Reutiliza toda la config de package.json pero redirige la salida fuera de
 * `Documents/` para evitar el lock de Windows Defender / Search Indexer sobre
 * el .asar recién creado (causa del "file in use" en app.asar).
 */
const path = require('path');
const pkg = require('./package.json');

module.exports = {
  ...pkg.build,
  directories: {
    ...(pkg.build && pkg.build.directories),
    output: 'C:/pos-build-out',
  },
};
