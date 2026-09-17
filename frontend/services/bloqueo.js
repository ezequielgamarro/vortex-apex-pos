/**
 * bloqueo.js — Pantalla de LICENCIA VENCIDA y activación por CÓDIGO FIRMADO.
 *
 * FLUJO (Etapa 2, modelo desafío-respuesta):
 *   1. El POS muestra su HUELLA de máquina (la trae del backend: GET /licencia/huella).
 *   2. El cliente COPIA la huella y se la envía al proveedor (WhatsApp).
 *   3. El proveedor devuelve un CÓDIGO FIRMADO (VX1....).
 *   4. El cliente lo pega y el backend lo VERIFICA con la llave pública Ed25519.
 *
 * SEGURIDAD: el frontend NUNCA conoce la llave ni decide fechas; solo transporta
 * el código. La verificación y las fechas viven en el backend (single source).
 */
import api, { clearSession } from './api.js';

document.addEventListener('DOMContentLoaded', async () => {
  const panel = document.getElementById('activacion-panel');
  const form = document.getElementById('activacion-form');
  const errorEl = document.getElementById('activacion-error');
  const successEl = document.getElementById('activacion-success');
  const btnLogout = document.getElementById('btn-logout');

  const inputHuella = document.getElementById('licencia-huella');
  const btnCopiarHuella = document.getElementById('btn-copiar-huella');
  const btnWhatsapp = document.getElementById('btn-whatsapp');
  const inputCodigo = document.getElementById('licencia-codigo');

    const msjEl = document.getElementById('bloqueo-mensaje');
  const contactoEl = document.getElementById('bloqueo-contacto');

  const btnDescargar = document.getElementById('btn-descargar-datos');
  const descargaMsg = document.getElementById('descarga-msg');

  const rol = localStorage.getItem('rol');
  let datosHuella = null; // { cliente_id, huella }

    btnLogout.addEventListener('click', () => {
    clearSession();
    window.location.replace('login.html');
  });

  // ---------------------------------------------------------------
  // 0) Descarga de respaldo completo (solo admin).
  //    El comercio SIEMPRE puede recuperar sus datos, aun sin pagar
  //    (principio de no secuestrar la información del cliente).
  // ---------------------------------------------------------------
  if (btnDescargar) {
    if (rol !== 'admin') {
      // El cajero no exporta el respaldo completo: se oculta el botón.
      btnDescargar.style.display = 'none';
    } else {
      btnDescargar.addEventListener('click', async () => {
        btnDescargar.disabled = true;
        const textoOriginal = btnDescargar.textContent;
        btnDescargar.textContent = 'Generando respaldo…';
        descargaMsg.classList.add('hidden');
        try {
          await api.exportarTodoExcel();
          descargaMsg.textContent = 'Respaldo descargado correctamente.';
          descargaMsg.className = 'text-center text-xs mt-2 text-green-600';
          descargaMsg.classList.remove('hidden');
        } catch (error) {
          descargaMsg.textContent =
            error.message || 'No se pudo generar el respaldo.';
          descargaMsg.className = 'text-center text-xs mt-2 text-pos-danger';
          descargaMsg.classList.remove('hidden');
        } finally {
          btnDescargar.disabled = false;
          btnDescargar.textContent = textoOriginal;
        }
      });
    }
  }

  // ---------------------------------------------------------------
  // 1) Estado de la licencia (mensaje + datos de contacto).
  // ---------------------------------------------------------------
  try {
    const estado = await api.licenciaEstado();
    msjEl.textContent = estado.mensaje ||
      'El acceso al sistema ha sido suspendido por falta de pago.';
    if (estado.contacto) {
      contactoEl.textContent = `Por favor, comuníquese con: ${estado.contacto}`;
    }
  } catch (error) {
    if (error.status === 401 || error.status === 403) {
      clearSession();
      window.location.replace('login.html');
      return;
    }
    console.error('Error al obtener estado de licencia:', error);
  }

  // ---------------------------------------------------------------
  // 2) Panel de activación (solo admin): cargar la huella de la máquina.
  // ---------------------------------------------------------------
  if (rol === 'admin' && panel) {
    panel.classList.remove('hidden');
    try {
      datosHuella = await api.licenciaHuella();
      inputHuella.value = datosHuella.huella || '';
    } catch (error) {
      console.error('No se pudo obtener la huella:', error);
      inputHuella.value = '(no disponible)';
    }
  }

  // ---------------------------------------------------------------
  // 3) Botón COPIAR huella (para pegarla donde quiera el cliente).
  // ---------------------------------------------------------------
  if (btnCopiarHuella) {
    btnCopiarHuella.addEventListener('click', async () => {
      const texto = inputHuella.value;
      try {
        await navigator.clipboard.writeText(texto);
        const original = btnCopiarHuella.textContent;
        btnCopiarHuella.textContent = '¡Copiado!';
        setTimeout(() => { btnCopiarHuella.textContent = original; }, 1500);
      } catch (_) {
        // Fallback para navegadores sin clipboard API.
        inputHuella.select();
        document.execCommand('copy');
      }
    });
  }

  // ---------------------------------------------------------------
  // 4) Botón WhatsApp (opcional): abre el chat con el mensaje ya escrito.
  //    NO usa internet del POS: solo abre wa.me; el envío lo hace el teléfono.
  // ---------------------------------------------------------------
  if (btnWhatsapp) {
    const contacto = CONTACTO_WHATSAPP(); // número del proveedor (config).
    if (contacto) {
      btnWhatsapp.classList.remove('hidden');
      btnWhatsapp.addEventListener('click', () => {
        const huella = inputHuella.value || '';
        const cid = (datosHuella && datosHuella.cliente_id) || '';
        const mensaje = encodeURIComponent(
          `Hola, solicito activación de licencia.\nCliente: ${cid}\nHuella: ${huella}`
        );
        window.open(`https://wa.me/${contacto}?text=${mensaje}`, '_blank');
      });
    }
  }

  // ---------------------------------------------------------------
  // 5) Enviar el código firmado al backend para verificar y activar.
  // ---------------------------------------------------------------
  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      errorEl.classList.add('hidden');
      successEl.classList.add('hidden');

      const codigo = (inputCodigo.value || '').trim();
      if (!codigo) {
        errorEl.textContent = 'Pegá el código de activación recibido.';
        errorEl.classList.remove('hidden');
        return;
      }

      const btn = document.getElementById('btn-activar');
      btn.disabled = true;
      btn.textContent = 'Verificando...';

      try {
        await api.licenciaActivar({ codigo_firmado: codigo });

        successEl.textContent = 'Licencia activada con éxito. Redirigiendo...';
        successEl.classList.remove('hidden');

        setTimeout(() => {
          window.location.replace('pos.html');
        }, 1500);
      } catch (error) {
        errorEl.textContent = error.message || 'Código de activación rechazado.';
        errorEl.classList.remove('hidden');
      } finally {
        btn.disabled = false;
        btn.textContent = 'Activar Licencia';
      }
    });
  }
});

/**
 * Número de WhatsApp del proveedor (formato internacional, solo dígitos).
 * Se define en window.WHATSAPP_PROVEEDOR desde config.js si existe; si no,
 * el botón no se muestra (la copia manual sigue disponible).
 */
function CONTACTO_WHATSAPP() {
  const n = (window.WHATSAPP_PROVEEDOR || '').replace(/\D/g, '');
  return n;
}
