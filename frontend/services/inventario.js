/**
 * inventario.js — CRUD de Productos.
 * Lista, crea, edita y elimina productos conectándose a /api/productos.
 *
 * Módulos integrados:
 *   - Módulo 1 (multi-rubro): muestra talle/color/vencimiento según el rubro.
 *   - Módulo 2 (Excel): exportar/importar catálogo .xlsx (botones del HTML).
 */
import { api } from './api.js';
import { mostrarAlerta } from './ui.js';

const $ = (id) => document.getElementById(id);

const money = (n) =>
  new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP' }).format(n);

/**
 * Normaliza los campos que el backend Pydantic serializa como JSON string
 * (Decimales: precio, costo, stock, stock_minimo). El render y las
 * comparaciones de stock deben operar con Number para que la lógica de
 * "bajo stock" sea correcta. `activo`, `id` (UUID) y `tipo_unidad` se mantienen.
 */
function normalizarProducto(p) {
  const out = { ...p };
  ['precio', 'costo', 'stock', 'stock_minimo'].forEach((k) => {
    const v = out[k];
    if (v !== undefined && v !== null && v !== '') out[k] = Number(v);
  });
  return out;
}

let productos = [];
let rolActual = 'cajero';
let categorias = [];            // lista maestra de categorías (para select)
let ordenCol = 'nombre';
let ordenDir = 'asc';
let terminoBusqueda = '';       // filtro en vivo (nombre / código de barras)
let filtroMarca = '';           // filtros específicos indumentaria
let filtroTalle = '';
let filtroColor = '';

/**
 * Normaliza texto para búsqueda: minúsculas y sin acentos.
 * Permite que "cafe" encuentre "Café" (UX esperable en un buscador).
 */
function normalizarTexto(s) {
  return String(s || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');
}

/**
 * Aplica el término de búsqueda sobre el catálogo cargado (client-side).
 * Coincide si el término aparece en el nombre o en el código de barras.
 * Cuando no hay término, devuelve el arreglo completo sin copiar.
 */
function productosFiltrados() {
  const q = normalizarTexto(terminoBusqueda).trim();
  const qMarca = normalizarTexto(filtroMarca).trim();
  const qTalle = normalizarTexto(filtroTalle).trim();
  const qColor = normalizarTexto(filtroColor).trim();
  return productos.filter((p) => {
    if (q && !normalizarTexto(p.nombre).includes(q) && !normalizarTexto(p.codigo_barras).includes(q)) return false;
    if (qMarca && !normalizarTexto(p.marca || '').includes(qMarca)) return false;
    if (qTalle && !normalizarTexto(p.talle || '').includes(qTalle)) return false;
    if (qColor && !normalizarTexto(p.color || '').includes(qColor)) return false;
    return true;
  });
}

/** Determina si la vista es de admin (para activar edición/creación). */
function esAdmin() {
  try {
    const u = JSON.parse(localStorage.getItem('user') || 'null');
    return u?.rol === 'admin';
  } catch {
    return false;
  }
}

/** Rubro del negocio (multi-rubro). Define qué campos extra se muestran. */
function rubroActual() {
  try {
    const u = JSON.parse(localStorage.getItem('user') || 'null');
    return u?.rubro || 'general';
  } catch {
    return 'general';
  }
}

/**
 * Muestra u oculta los campos específicos del rubro en el modal.
 *   - 'indumentaria'        -> talle + color
 *   - 'panaderia_alimentos' -> fecha de vencimiento
 * Estructura declarativa: agregar rubro = agregar un caso aquí.
 */
function aplicarRubroUI() {
  const rubro = rubroActual();
  // Indumentaria agrupa los 3 atributos (marca/talle/color) bajo un mismo
  // contenedor declarativo `data-rubro="talle"` en el HTML. Se conserva ese
  // contenedor como single source of truth para mostrar/ocultar el bloque.
  const showRopa = rubro === 'indumentaria';
  const showVenc = rubro === 'panaderia_alimentos';
  document.querySelectorAll('[data-rubro="talle"], [data-rubro="marca"], [data-rubro="color"]').forEach((el) => {
    el.classList.toggle('hidden', !showRopa);
  });
  document.querySelectorAll('[data-rubro="vencimiento"]').forEach((el) => {
    el.classList.toggle('hidden', !showVenc);
  });
  
  const tipoSelect = $('prod-tipo');
  if (tipoSelect) {
    const showPesoPorcion = (rubro === 'panaderia_alimentos' || rubro === 'general');
    Array.from(tipoSelect.options).forEach(opt => {
      if (opt.value === 'peso' || opt.value === 'porcion') {
        opt.style.display = showPesoPorcion ? '' : 'none';
        opt.disabled = !showPesoPorcion;
      }
    });
    if (tipoSelect.options[tipoSelect.selectedIndex]?.disabled) {
      tipoSelect.value = 'unidad';
    }
  }
  
  // Mostrar/ocultar barra de filtros indumentaria
  const barraIndumentaria = $('filtros-indumentaria');
  if (barraIndumentaria) {
    const esRopa = (rubro === 'indumentaria');
    barraIndumentaria.classList.toggle('hidden', !esRopa);
    barraIndumentaria.classList.toggle('flex', esRopa);
  }
}

function toggleModales() {
  const esAdminFlag = esAdmin();
  const btnNuevo = $('btn-nuevo');
  if (btnNuevo) btnNuevo.style.display = esAdminFlag ? 'inline-flex' : 'none';
  // Importar Excel: solo admin. Exportar: cualquier usuario.
  const btnImportar = $('btn-importar');
  if (btnImportar) btnImportar.style.display = esAdminFlag ? 'inline-flex' : 'none';
  document.getElementById('aviso-admin')?.classList.toggle('hidden', esAdminFlag);
}

// ---- Toolbar del inventario (filtros y orden consultados al backend) ----
function construirQueryToolbar() {
  const params = new URLSearchParams();
  const cat = $('filtro-categoria')?.value || '';
  const est = $('filtro-estado')?.value || '';
  const act = $('filtro-activo')?.value || '';

  if (cat) params.set('categoria', cat);
  if (est) params.set('estado_stock', est);
  if (act) params.set('activo', act);
  params.set('orden', ordenCol);
  params.set('dir', ordenDir);

  const qs = params.toString();
  return qs ? `?${qs}` : '';
}

/** Rellena el select de filtro por categoría y el select del modal. */
async function rellenarSelectsCategoria(valor = '') {
  try {
    const arr = await api.getCategories();
    categorias = Array.isArray(arr) ? arr : [];
  } catch (_) {
    categorias = [];
  }
  // Filtrar select de la tabla
  const fCat = $('filtro-categoria');
  if (fCat) {
    const actual = fCat.value;
    fCat.innerHTML =
      '<option value="">Todas</option>' +
      categorias
        .map((c) => `<option value="${c.nombre}">${c.nombre}</option>`)
        .join('') +
      (Array.isArray(productos)
        ? [...new Set(productos.map((p) => p.categoria).filter(Boolean))]
            .filter((n) => !categorias.some((c) => c.nombre === n))
            .map((n) => `<option value="${n}">${n}</option>`)
            .join('')
        : '');
    if ([...fCat.options].some((o) => o.value === actual)) fCat.value = actual;
  }
  // Select de categoría dentro del modal de producto
  const pCat = $('prod-categoria');
  if (pCat) {
    const actual = pCat.value;
    pCat.innerHTML =
      '<option value="">Sin categoría</option>' +
      categorias.map((c) => `<option value="${c.nombre}">${c.nombre}</option>`).join('');
    if ([...pCat.options].some((o) => o.value === actual)) pCat.value = actual;
  }
}

/** Renderiza la tabla de productos (respetando el filtro de búsqueda en vivo). */
function renderTabla() {
  const tbody = $('tabla-productos');
  tbody.innerHTML = '';

  const visibles = productosFiltrados();

  // Sin productos cargados (catálogo vacío en el backend).
  if (!productos.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="text-center text-pos-text-body/60 py-8">No hay productos registrados.</td></tr>';
    return;
  }

  // Hay catálogo pero la búsqueda no encontró coincidencias.
  if (!visibles.length) {
    const term = terminoBusqueda.trim();
    tbody.innerHTML = `<tr><td colspan="7" class="text-center text-pos-text-body/60 py-8">Sin resultados para "${term}".</td></tr>`;
    return;
  }

  const admin = esAdmin();

  visibles.forEach((p) => {
    const bajo = p.stock <= p.stock_minimo;
    const tipo = p.tipo_unidad || 'unidad';
    const etiquetaTipo = tipo === 'peso' ? 'Peso' : (tipo === 'porcion' ? 'Porción' : 'Unidad');
    // Aviso de vencimiento (solo si el producto trae fecha).
    let vencBadge = '';
    if (p.fecha_vencimiento) {
      const dias = Math.ceil((new Date(p.fecha_vencimiento) - new Date()) / 86400000);
      if (dias < 0) vencBadge = ' <span class="badge badge-danger ml-1">Vencido</span>';
      else if (dias <= 7) vencBadge = ` <span class="badge badge-neutral ml-1">Vence ${dias}d</span>`;
    }
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="font-mono text-xs">${p.codigo_barras || '—'}</td>
      <td class="font-medium">
        ${p.nombre} <span class="badge badge-neutral ml-1 align-middle">${etiquetaTipo}</span>${vencBadge}
      </td>
      <td>${p.categoria || '—'}</td>
      <td>${money(p.precio)}</td>
      <td>
        <span class="badge ${bajo ? 'badge-danger' : 'badge-neutral'}">${p.stock}</span>
      </td>
      <td>
        <span class="badge ${p.activo ? 'badge-primary' : 'badge-neutral'}">${p.activo ? 'Activo' : 'Inactivo'}</span>
      </td>
      <td>
        <div class="flex justify-end gap-2">
          ${admin ? `
            <button data-editar="${p.id}" class="btn-secondary !px-3 !py-1.5 text-xs">Editar</button>
            <button data-eliminar="${p.id}" class="btn-danger !px-3 !py-1.5 text-xs">Eliminar</button>
          ` : ''}
        </div>
      </td>`;
    tbody.appendChild(tr);
  });

  // Enlazar acciones si es admin
  if (admin) {
    tbody.querySelectorAll('[data-editar]').forEach((b) =>
      b.addEventListener('click', () => abrirEdicion(b.dataset.editar))
    );
    tbody.querySelectorAll('[data-eliminar]').forEach((b) =>
      b.addEventListener('click', () => confirmarEliminar(b.dataset.eliminar))
    );
  }
}

// ---- Crear / Editar ----
function calcularPrecioSugerido() {
  const costo = Number($('prod-costo')?.value || 0);
  const margen = Number($('prod-margen')?.value || 0);
  const ap = Number($('prod-precio')?.value || 0);
  const sugerido = costo > 0 && margen >= 0 ? costo + (costo * margen) / 100 : null;

  // Muestra pista informativa con el valor que auto-aplicaría por costo+margen.
  const hint = $('sugerencia-precio');
  if (hint) {
    if (sugerido !== null && ap > 0 && Math.abs(ap - sugerido) > 0.009) {
      hint.textContent = `Precio según Costo + Margen: ${money(sugerido)}. Puedés dejarlo así o corregirlo (override manual).`;
    } else if (sugerido !== null && ap <= 0) {
      hint.textContent = `Con Costo ${money(costo)} y margen ${margen}% el precio sugerido es ${money(sugerido)}. Se aplicará al guardar si no lo pisás.`;
    } else {
      hint.textContent = 'El precio se auto-calcula con Costo + Margen %. Podés redondearlo o corregirlo manualmente.';
    }
  }
  return sugerido;
}

/** Auto-aplica el precio por costo+margen SOLO si el cajero no lo ajustó a mano;
 *  si lo modifica, respeta el override. Dispara desde inputs costo/margen. */
function autocalcularPrecio() {
  const costo = Number($('prod-costo')?.value || 0);
  const margen = Number($('prod-margen')?.value || 0);
  if (costo > 0 && margen >= 0) {
    $('prod-precio').value = (costo + (costo * margen) / 100).toFixed(2);
  }
  calcularPrecioSugerido();
}

function abrirModal(titulo = 'Nuevo producto', prod = null) {
  $('modal-producto-titulo').textContent = titulo;
  $('prod-id').value = prod?.id || '';
  $('prod-nombre').value = prod?.nombre || '';
  $('prod-codigo').value = prod?.codigo_barras || '';
  $('prod-precio').value = prod?.precio ?? '';
  $('prod-costo').value = prod?.costo ?? '';
  $('prod-margen').value = prod?.porcentaje_ganancia ?? '';
  $('prod-stock').value = prod?.stock ?? '';
  $('prod-stock-min').value = prod?.stock_minimo ?? '';
  $('prod-descripcion').value = prod?.descripcion || '';
  $('prod-tipo').value = prod?.tipo_unidad || 'unidad';
  // Campos multi-rubro (existen en el DOM; se ocultan por CSS si no aplican).
  const elMarca = $('prod-marca');
  if (elMarca) elMarca.value = prod?.marca || '';
  const elTalle = $('prod-talle');
  if (elTalle) elTalle.value = prod?.talle || '';
  const elColor = $('prod-color');
  if (elColor) elColor.value = prod?.color || '';
  const elVenc = $('prod-vencimiento');
  if (elVenc) {
    elVenc.value = prod?.fecha_vencimiento
      ? String(prod.fecha_vencimiento).slice(0, 10)
      : '';
  }
  aplicarRubroUI();
  $('prod-activo').checked = prod ? !!prod.activo : true;
  // Select de categoría: conserva la elegida (server-side list).
  const valCat = prod?.categoria || '';
  $('prod-categoria').innerHTML =
    '<option value="">Sin categoría</option>' +
    categorias.map((c) => `<option value="${c.nombre}">${c.nombre}</option>`).join('') +
    (!categorias.some((c) => c.nombre === valCat) && valCat
      ? `<option value="${valCat}" selected>${valCat}</option>`
      : '');
  $('prod-categoria').value = valCat || '';

  calcularPrecioSugerido();

  $('modal-producto').classList.remove('hidden');
  $('modal-producto').classList.add('flex');
  $('prod-nombre').focus();
}

function abrirEdicion(id) {
  const p = productos.find((x) => x.id === id);
  if (p) abrirModal('Editar producto', p);
}

// ---- Eliminar ----
let idAEliminar = null;
function confirmarEliminar(id) {
  idAEliminar = id;
  $('modal-eliminar').classList.remove('hidden');
  $('modal-eliminar').classList.add('flex');
}

// ---- Guardar (create/update) ----
async function guardar(e) {
  e.preventDefault();
  const id = $('prod-id').value;
  const precio = Number($('prod-precio').value || 0);
  const payload = {
    nombre: $('prod-nombre').value.trim(),
    codigo_barras: $('prod-codigo').value.trim() || null,
    categoria: $('prod-categoria').value || null,
    tipo_unidad: $('prod-tipo').value || 'unidad',
    precio,
    costo: Number($('prod-costo').value || 0),
    porcentaje_ganancia: Number($('prod-margen').value || 0),
    stock: Number($('prod-stock').value || 0),
    stock_minimo: Number($('prod-stock-min').value || 0),
    descripcion: $('prod-descripcion').value.trim() || null,
    activo: $('prod-activo').checked,
    // Campos multi-rubro (se envían siempre; el backend los acepta opcionales).
    marca: $('prod-marca')?.value.trim() || null,
    talle: $('prod-talle')?.value.trim() || null,
    color: $('prod-color')?.value.trim() || null,
    fecha_vencimiento: $('prod-vencimiento')?.value
      ? `${$('prod-vencimiento').value}T00:00:00`
      : null,
  };
  if (!(precio > 0)) { mostrarAlerta('El precio de venta debe ser mayor a cero.', 'error'); return; }

  try {
    if (id) {
      await api.updateProduct(id, payload);
    } else {
      await api.createProduct(payload);
    }
    cerrarModal('modal-producto');
    await cargar();
    await rellenarSelectsCategoria();
  } catch (err) {
    mostrarAlerta(`Error al guardar: ${err.message}`, 'error');
  }
}

// ---- NUEVA CATEGORÍA (modal rápido) ----
function abrirModalCategoria() {
  $('categoria-nuevo-nombre').value = '';
  $('modal-nueva-categoria').classList.remove('hidden');
  $('modal-nueva-categoria').classList.add('flex');
  $('categoria-nuevo-nombre').focus();
}
function cerrarModalCategoria() {
  const m = $('modal-nueva-categoria');
  if (m) { m.classList.add('hidden'); m.classList.remove('flex'); }
}
async function crearCategoria() {
  if (!esAdmin()) {
    mostrarAlerta('Sólo el administrador puede crear categorías.', 'warn');
    cerrarModalCategoria();
    return;
  }
  const nombre = ($('categoria-nuevo-nombre').value || '').trim();
  if (!nombre) { mostrarAlerta('Ingresa el nombre de la categoría.', 'error'); return; }
  try {
    const cat = await api.createCategory({ nombre });
    cerrarModalCategoria();
    await rellenarSelectsCategoria();
    if (cat?.nombre) $('prod-categoria').value = cat.nombre;
  } catch (err) {
    mostrarAlerta(`No se pudo crear la categoría: ${err.message}`, 'error');
  }
}

// ---- Eliminar confirmado ----
async function eliminar() {
  if (!idAEliminar) return;
  try {
    await api.deleteProduct(idAEliminar);
    cerrarModal('modal-eliminar');
    idAEliminar = null;
    await cargar();
  } catch (err) {
    mostrarAlerta(`Error al eliminar: ${err.message}`, 'error');
  }
}

function cerrarModal(id) {
  const m = document.getElementById(id);
  m.classList.add('hidden');
  m.classList.remove('flex');
}

// ---- Módulo 2: Exportar / Importar Excel ----
async function exportarExcel() {
  try {
    mostrarAlerta('Generando Excel…', 'ok');
    await api.exportProductsExcel();
  } catch (err) {
    mostrarAlerta(`No se pudo exportar: ${err.message}`, 'error');
  }
}

async function importarExcel(file) {
  if (!file) return;
  try {
    mostrarAlerta('Importando… esto puede tardar unos segundos.', 'ok');
    const res = await api.importProductsExcel(file);
    const detalle = res?.errores?.length
      ? `\nFilas con error: ${res.errores
          .slice(0, 5)
          .map((e) => `fila ${e.fila} (${e.error})`)
          .join('; ')}`
      : '';
    const msj = (res?.mensaje || 'Importación finalizada.') + detalle;
    mostrarAlerta(
      msj,
      res?.omitidos ? 'warn' : 'ok'
    );
    await cargar();
    await rellenarSelectsCategoria();
  } catch (err) {
    mostrarAlerta(`No se pudo importar: ${err.message}`, 'error');
  } finally {
    // Permite reimportar el mismo archivo sin recargar la página.
    const inp = $('input-importar');
    if (inp) inp.value = '';
  }
}

/** Carga productos desde el backend (aplicando filtros/orden del toolbar). */
async function cargar() {
  try {
    const qs = construirQueryToolbar();
    const arr = await api.getProducts(qs);
    // El backend Pydantic envía Decimales como JSON string → normalizar.
    productos = (Array.isArray(arr) ? arr : []).map(normalizarProducto);
    renderTabla();
    await rellenarSelectsCategoria();
  } catch (e) {
    $('tabla-productos').innerHTML =
      `<tr><td colspan="7" class="text-center text-pos-danger py-8">No se pudieron cargar los productos: ${e.message}</td></tr>`;
  }
}

function alternarOrden() {
  const ico = $('ico-orden');
  // Alterna dirección (asc↔desc) y refresca.
  ordenDir = ordenDir === 'asc' ? 'desc' : 'asc';
  if (ico) {
    // Rota visualmente para indicar el sentido (simple, sin librerías).
    ico.style.transform = ordenDir === 'desc' ? 'rotate(180deg)' : 'rotate(0deg)';
  }
  cargar();
}

// ---- Inicialización bajo guardia de seguridad ----
async function init() {
  if (window.authGuardReady) {
    await window.authGuardReady;
  }

  $('btn-nuevo').addEventListener('click', () => abrirModal());
  $('form-producto').addEventListener('submit', guardar);
  $('btn-confirmar-eliminar').addEventListener('click', eliminar);

  // Modal nueva categoría (sólo admin; los cajeros sólo eligen categorías).
  const bCat = $('btn-nueva-categoria');
  if (bCat) {
    if (!esAdmin()) bCat.style.display = 'none';
    else bCat.addEventListener('click', abrirModalCategoria);
  }
  const bCatGui = $('btn-categoria-guardar');
  if (bCatGui) bCatGui.addEventListener('click', crearCategoria);
  const bCatCerrar = $('btn-categoria-cerrar');
  if (bCatCerrar) bCatCerrar.addEventListener('click', cerrarModalCategoria);
  const bCatCancel = document.querySelector('[data-close-cat]');
  if (bCatCancel) bCatCancel.addEventListener('click', cerrarModalCategoria);

  // ---- Módulo 2: botones Excel ----
  $('btn-exportar')?.addEventListener('click', exportarExcel);
  $('btn-importar')?.addEventListener('click', () => $('input-importar')?.click());
  $('input-importar')?.addEventListener('change', (e) => {
    const file = e.target.files && e.target.files[0];
    importarExcel(file);
  });

  // Auto-cálculo de Precio = Costo + Margen %, con override manual editable.
  const inpCosto = $('prod-costo');
  const inpMargen = $('prod-margen');
  if (inpCosto) inpCosto.addEventListener('input', autocalcularPrecio);
  if (inpMargen) inpMargen.addEventListener('input', autocalcularPrecio);
  const inpPrecio = $('prod-precio');
  if (inpPrecio) inpPrecio.addEventListener('input', calcularPrecioSugerido);

  // Toolbar (filtros y orden), refrescan contra el backend.
  ['filtro-categoria', 'filtro-estado', 'filtro-activo', 'orden-col'].forEach((id) => {
    const el = $(id);
    if (el) el.addEventListener('change', () => {
      if (id === 'orden-col') ordenCol = el.value;
      cargar();
    });
  });
  const bOrden = $('btn-orden-dir');
  if (bOrden) bOrden.addEventListener('click', alternarOrden);

    // Buscador en vivo (nombre / código de barras): filtra lo ya cargado sin
  // volver al backend. Sólo re-renderiza la tabla (no recarga ni pierde foco).
  const buscador = $('buscar-producto');
  if (buscador) {
    buscador.addEventListener('input', () => {
      terminoBusqueda = buscador.value;
      renderTabla();
    });
  }

  // Filtros específicos de indumentaria (Marca/Talle/Color): filtrado
  // client-side sobre el catálogo ya cargado. No requieren round-trip al
  // backend porque el catálogo por rubro es acotado y la respuesta es inmediata.
  ['filtro-marca', 'filtro-talle', 'filtro-color'].forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.addEventListener('input', () => {
      filtroMarca = $('filtro-marca')?.value || '';
      filtroTalle = $('filtro-talle')?.value || '';
      filtroColor = $('filtro-color')?.value || '';
      renderTabla();
    });
  });

  // Botón "Limpiar" de los filtros de ropa: resetea los tres campos.
  const btnLimpiarRopa = $('btn-limpiar-filtros-ropa');
  if (btnLimpiarRopa) {
    btnLimpiarRopa.addEventListener('click', () => {
      ['filtro-marca', 'filtro-talle', 'filtro-color'].forEach((id) => {
        const el = $(id);
        if (el) el.value = '';
      });
      filtroMarca = filtroTalle = filtroColor = '';
      renderTabla();
    });
  }

  toggleModales();
  aplicarRubroUI();
  await cargar();
}

init();