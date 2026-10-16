// Corta el build firmado si falta el certificado, en vez de generar un
// instalador sin firmar sin avisar. electron-builder firma solo cuando ve
// CSC_LINK (ruta al .pfx/.p12 o su contenido en base64) y CSC_KEY_PASSWORD.
const falta = ['CSC_LINK', 'CSC_KEY_PASSWORD'].filter((v) => !process.env[v]);
if (falta.length) {
  console.error(
    `\n[FIRMA] Faltan variables de entorno: ${falta.join(', ')}.\n` +
      'Definilas con el certificado de firma de código y volvé a correr "npm run dist:firmado".\n' +
      'Ver docs/OPERACION.md, sección "Firmar el instalador".\n'
  );
  process.exit(1);
}
console.log('[FIRMA] Certificado configurado: el instalador y el .exe se van a firmar.');
