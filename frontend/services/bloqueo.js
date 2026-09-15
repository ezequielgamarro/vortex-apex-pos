import api, { clearSession } from './api.js';

document.addEventListener('DOMContentLoaded', async () => {
  const form = document.getElementById('activacion-form');
  const errorEl = document.getElementById('activacion-error');
  const successEl = document.getElementById('activacion-success');
  const btnLogout = document.getElementById('btn-logout');
  
  const inputClienteId = document.getElementById('licencia-cliente-id');
  const inputFecha = document.getElementById('licencia-fecha');
  const inputGracia = document.getElementById('licencia-gracia');
  const inputClave = document.getElementById('licencia-clave');
  
  const msjEl = document.getElementById('bloqueo-mensaje');
  const contactoEl = document.getElementById('bloqueo-contacto');

  let rol = localStorage.getItem('rol');
  
  btnLogout.addEventListener('click', () => {
    clearSession();
    window.location.replace('login.html');
  });

  try {
    const estado = await api.licenciaEstado();
    msjEl.textContent = estado.mensaje || 'El acceso al sistema ha sido suspendido por falta de pago.';
    if (estado.contacto) {
        contactoEl.textContent = `Por favor, comuníquese con: ${estado.contacto}`;
    }
    
    if (rol === 'admin') {
      form.classList.remove('hidden');
      inputClienteId.value = estado.cliente_id || '';
    }
  } catch (error) {
     if (error.status === 401 || error.status === 403) {
         clearSession();
         window.location.replace('login.html');
     } else {
         console.error('Error al obtener estado de licencia:', error);
     }
  }

  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      errorEl.classList.add('hidden');
      successEl.classList.add('hidden');
      
      const btn = document.getElementById('btn-activar');
      btn.disabled = true;
      btn.textContent = 'Activando...';

      try {
        const payload = {
          cliente_id: inputClienteId.value,
          fecha_vencimiento: inputFecha.value ? new Date(inputFecha.value).toISOString() : '',
          dias_gracia: parseInt(inputGracia.value) || 0,
          clave_activacion: inputClave.value
        };
        
        await api.licenciaActivar(payload);
        
        successEl.textContent = 'Licencia activada con éxito. Redirigiendo...';
        successEl.classList.remove('hidden');
        
        setTimeout(() => {
          window.location.replace('pos.html');
        }, 1500);
        
      } catch (error) {
        errorEl.textContent = error.message || 'Error al activar la licencia.';
        errorEl.classList.remove('hidden');
      } finally {
        btn.disabled = false;
        btn.textContent = 'Activar Licencia';
      }
    });
  }
});
