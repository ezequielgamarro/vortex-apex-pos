/**
 * pos.js — Lógica del Terminal POS.
 *
 * Carga el catálogo, maneja el carrito y registra la venta contra el backend
 * local FastAPI (`api.registerSale`). Soporta **unidades de venta**:
 *   - 'unidad' / 'porcion': se agregan por pieza entera (cantidad entera).
 *   - 'peso': el cajero ingresa KILOS (cantidad) O IMPORTE ($). El backend
 *     deriva la cantidad física exacta y descuenta la fracción de stock.
 *
 * Payload enviado al backend (esquema venta.VentaItem):
 *   { producto_id, cantidad }   → para piezas o venta por peso (kilos)
 *   { producto_id, importe }    → para venta por peso en pesos ($)
 */
import { api } from './api.js';
import { mostrarAlerta, exponerUIglobal } from './ui.js';
import { instalarAtajosPOS } from './atajos.js';
import { instalarLector, normalizarCodigo } from './lector.js';

const $ = (id) => document.getElementById(id);

/**
 * ¿Hay algún modal abierto? Los modales del POS se muestran alternando las
 * clases `hidden`/`flex` sobre un contenedor con id `modal-*` (o `modal-*` con
 * sufijo). Sirve como *guard clause* para que listeners globales acotados
 * (p. ej. el disparo del escáner con Enter) no roben eventos mientras el
 * usuario interactúa con un modal.
 */
function modalActivo() {
  return !!document.querySelector('[id^="modal-"].flex');
}

const money = (n) =>
  new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP' }).format(n || 0);

/** Escapa HTML para evitar inyección al construir el ticket (nombre negocio/cliente). */
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

// ---------- Estado del carrito ----------
// Línea: { producto, modo, cantidad?, importe? } según unidad de venta.
//   modo 'unidad'/'porcion'  →  cantidad entera
//   modo 'cantidad' (peso)   →  cantidad en kg
//   modo 'importe'   (peso)  →  importe en $
let carrito = [];
let catalogo = [];          // resultado ACTUAL mostrado en el grid (puede ser filtrado)
let catalogoCompleto = [];  // catálogo total de la BD (ref. p/ búsqueda vacía y conteo)
let clientesCC = [];         // clientes disponibles para venta a cuenta corriente
let productoPesoActual = null; // producto que se está cargando en el modal de peso
// Snapshot de la última venta confirmada (folio, items, total, método, cliente)
// para el modal "Venta Completada" y la impresión opcional del comprobante.
let ventaUltima = null;

// ---------- Helpers de producto ----------
// Unidades CONTINUAS: admiten fracciones y venta por importe ($). Se apoyan en
// la misma mecánica (ver `_resolver_item` del backend). Fuente única de verdad
// en el front: la lista. 'peso' se conserva por compatibilidad de nombre.
const TIPOS_CONTINUOS = ['peso', 'metros', 'litros'];

/** ¿El producto se vende por una unidad continua (kg / m / L)? */
function esPorPeso(p) { return TIPOS_CONTINUOS.includes(p.tipo_unidad || 'unidad'); }

/** ¿El producto es un servicio (librería: copia/impresión)? */
function esServicio(p) { return (p.tipo_unidad || 'unidad') === 'servicio'; }

/** Etiqueta corta de la unidad continua para textos de UI ('kg' | 'm' | 'L'). */
function etiquetaUnidadContinua(p) {
  const t = p.tipo_unidad || 'unidad';
  if (t === 'metros') return 'm';
  if (t === 'litros') return 'L';
  return 'kg';
}

/**
 * Estado de stock para las tarjetas del catálogo:
 *   - 'agotado' : stock === 0     → badge rojo "Agotado" (tarjeta deshabilitada).
 *   - 'poco'    : 0 < stock <= 5  → badge amarillo "Poco Stock".
 *   - 'ok'      : stock > 5.
 */
function estadoStock(p) {
  const s = Number(p?.stock ?? 0);
  if (s <= 0) return 'agotado';
  if (s <= 5) return 'poco';
  return 'ok';
}

/**
 * Etiqueta de unidad mostrada junto al precio en el catálogo.
 * Centraliza el texto para impedir duplicados del sufijo "kg" (bug "/kgkg"):
 *  - 'peso'    → "/kg"
 *  - 'porcion' → "/porción"
 *  - 'unidad'  → "/un." (precio por pieza)
 */
function sufijoUnidadPrecio(p) {
  const t = p.tipo_unidad || 'unidad';
  if (t === 'peso') return '/kg';
  if (t === 'metros') return '/m';
  if (t === 'litros') return '/L';
  if (t === 'servicio') return '/copia';
  if (t === 'porcion') return '/porción';
  return '/un.';
}

/**
 * Formatea la cantidad física (stock) para mostrarla en la tarjeta.
 * El backend entrega el stock como JSON string con ceros (p. ej. "36.000").
 *  - 'unidad' / 'porcion' → entero sin decimales (36, no "36.000").
 *  - 'peso'              → conserva decimales, pero sin ceros sobrantes ("1.5", no "1.500").
 */
function formatearStock(stock, tipo) {
  const n = Number(stock || 0);
  const continuo = TIPOS_CONTINUOS.includes(tipo || 'unidad');
  return continuo ? String(Number(n.toFixed(3))) : String(Math.trunc(n));
}

function unidadesDisponibles(linea) {
  const p = linea.producto;
  // Stock se mide en las mismas unidades que la venta (kg para peso, piezas para unidad)
  return Number(p.stock || 0);
}

/** Importe de una línea (para subtotal y envío). */
function importeLinea(linea) {
  if (linea.modo === 'importe') return Number(linea.importe || 0);
  return (Number(linea.cantidad || 0)) * Number(linea.producto.precio || 0);
}

/** Cantidad física de una línea (piezas o kg). */
function cantidadLinea(linea) {
  if (linea.modo === 'importe') {
    // kg = importe / precio (solo informativo; el backend calcula exacto)
    const p = Number(linea.producto.precio || 0);
    return p > 0 ? Number(linea.importe) / p : 0;
  }
  return Number(linea.cantidad || 0);
}

// ---------- Render catálogo ----------
/**
 * Pinta la grilla de productos.
 * - `productos`: lista a mostrar (puede ser el catálogo completo o un filtrado).
 * - `esFiltro` : true si proviene de una búsqueda; permite mostrar el mensaje
 *   de "sin coincidencias" sólo cuando la BD no está vacía.
 */
function renderCatalogo(productos, esFiltro = false) {
  catalogo = productos || [];
  const grid = $('pos-catalogo');
  grid.innerHTML = '';

  // Catálogo global vacío ⇒ único mensaje legítimo: no hay inventario.
  if (!catalogoCompleto.length) {
    grid.innerHTML = '<p class="col-span-full text-center text-pos-text-body/70 py-8">Sin productos. Agrega inventario primero.</p>';
    return;
  }

  const sinResultados = esFiltro && (!productos || !productos.length);
  if (sinResultados) {
    grid.innerHTML = '<p class="col-span-full text-center text-pos-text-body/70 py-8">No se encontraron coincidencias</p>';
    return;
  }

    productos.forEach((p) => {
    const pesos = esPorPeso(p);
    const servicio = esServicio(p);
    const tipo = p.tipo_unidad || 'unidad';
    // Sufijo único del precio (evita duplicados tipo "/kgkg").
    const sufPrecio = sufijoUnidadPrecio(p);
    // Stock formateado según la unidad: "36" para unidad, "1.5" para peso.
    const stockTxt = formatearStock(p.stock, tipo);
    const stockEstado = estadoStock(p); // 'ok' | 'poco' | 'agotado'
    // Servicios ilimitados (stock 0) nunca se marcan agotados.
    const agotado = stockEstado === 'agotado' && !servicio;

    const card = document.createElement('button');
    card.type = 'button';
    // Layout de la tarjeta: `flex flex-col justify-between h-full` mantiene la
    // forma (cabecera arriba, pie abajo) sin importar el alto del contenido.
    // `h-full` funciona porque el grid-item estira a la altura de la fila.
    // `min-w-0` evita que contenido largo (nombre/código) desborde su celda.
    card.className =
      'pos-card producto-card p-4 text-left min-w-0 h-full flex flex-col justify-between gap-2 ' +
      (agotado ? 'opacity-60 cursor-not-allowed' : '');
    card.disabled = agotado;
    card.innerHTML = `
      <div class="flex items-start justify-between gap-2 min-w-0">
        <h5 class="text-sm font-semibold text-pos-text-head min-w-0 flex-1 line-clamp-2">${esc(p.nombre)}</h5>
        <div class="flex flex-wrap justify-end gap-1 shrink-0">
          ${pesos ? '<span class="badge badge-neutral">por ' + etiquetaUnidadContinua(p) + '</span>' : ''}
          ${servicio ? '<span class="badge badge-neutral">servicio</span>' : ''}
        </div>
      </div>
      <p class="text-pos-text-body/70 text-xs truncate min-w-0">${esc(p.codigo_barras || 'Sin código')}</p>
      <div class="mt-auto flex flex-col gap-1.5 min-w-0">
        <span class="text-lg font-bold leading-none text-pos-text-head whitespace-nowrap">${money(p.precio)}<span class="text-xs font-medium text-pos-text-body/70">${sufPrecio}</span></span>
        <span class="inline-flex items-center gap-1.5 text-xs whitespace-nowrap ${agotado ? 'text-pos-danger font-semibold' : stockEstado === 'poco' && !servicio ? 'text-pos-warning font-semibold' : 'text-pos-text-body/80'}"><span class="h-1.5 w-1.5 rounded-full ${agotado ? 'bg-pos-danger' : stockEstado === 'poco' && !servicio ? 'bg-pos-warning' : 'bg-pos-success'}" aria-hidden="true"></span>${agotado ? 'Agotado' : servicio && Number(p.stock || 0) <= 0 ? 'ilimitado' : (stockEstado === 'poco' && !servicio ? 'Poco stock · ' + stockTxt : stockTxt + (pesos ? ' ' + etiquetaUnidadContinua(p) : ' en stock'))}</span>
      </div>`;
    card.addEventListener('click', () => onSelectProducto(p));
    grid.appendChild(card);
  });
}

/** Acción al tocar una tarjeta de producto. */
function onSelectProducto(p) {
  if (esServicio(p)) {
    abrirModalServicio(p);
    return;
  }
  if (esPorPeso(p)) {
    abrirModalPeso(p);
    return;
  }
  // Unidad / porción: +1
  agregarUnidad(p, 1);
}

// ---- ELEMENTOS UNITARIOS (unidad/porción) ----
function agregarUnidad(p, delta) {
  const idx = carrito.findIndex((l) => l.producto.id === p.id);
  const disponible = Number(p.stock || 0);

  if (idx >= 0) {
    carrito[idx].cantidad = (Number(carrito[idx].cantidad) || 0) + delta;
    if (carrito[idx].cantidad > disponible) {

      mostrarAlerta(`Stock insuficiente: máximo disponible ${disponible}.`, 'warn');
      carrito[idx].cantidad = disponible;
    }
    if (carrito[idx].cantidad <= 0) carrito.splice(idx, 1);
  } else {
    if (delta <= 0) return;
    carrito.push({ producto: p, modo: p.tipo_unidad || 'unidad', cantidad: delta });
  }
  renderCarrito();
}

// ---- PRODUCTOS POR PESO (modal kg / importe) ----

/**
 * Foco diferido y fiable sobre un input.
 *
 * PROBLEMA: al abrir el modal pasamos el contenedor de `display:none` (.hidden)
 * a `display:flex`. El `focus()` SÍNCRONO ocurre ANTES de que el navegador
 * compute el layout/reflow; sobre un elemento aún no maquetado el foco se
 * descarta silenciosamente (WebKit/Safari y Chrome con ciertas condiciones),
 * de modo que el input queda sin foco y el teclado no responde.
 *
 * SOLUCIÓN: forzar la reejecución del foco tras un `setTimeout(100ms)`, cuando
 * el modal ya está pintado y el input es realmente focusable. Mismo patrón
 * para el auto-select inicial (mejora la ergonomía del ingreso numérico).
 */
function focusInputDiferido(id, { seleccionar = false } = {}) {
  setTimeout(() => {
    const el = $(id);
    if (!el) return;
    el.focus();
    if (seleccionar && typeof el.select === 'function') {
      try { el.select(); } catch (_) { /* inputs number: select() puede no aplicar */ }
    }
  }, 100);
}

function abrirModalPeso(p) {
  productoPesoActual = p;
  const u = etiquetaUnidadContinua(p);
  $('peso-modal-titulo').textContent = p.nombre;
  $('peso-modal-precio').textContent = `${money(p.precio)} / ${u}   ·   stock: ${formatearStock(p.stock, p.tipo_unidad)} ${u}`;
  $('peso-modo-cantidad').checked = true;
  $('peso-modo-importe').checked = false;
  $('peso-valor').value = '';
  actualizarPlaceholder();

  const m = $('modal-peso');
  m.classList.remove('hidden');
  m.classList.add('flex');

  // Auto-focus + auto-select tras el reflow (ver focusInputDiferido).
  // 100ms: garantiza teclado numérico en móvil y foco estable en escritorio.
  focusInputDiferido('peso-valor', { seleccionar: true });
}

function actualizarPlaceholder() {
  const input = $('peso-valor');
  const esPorCantidad = $('peso-modo-cantidad').checked;
  const lbl = $('peso-valor-label');
  const u = productoPesoActual ? etiquetaUnidadContinua(productoPesoActual) : 'kg';
  if (esPorCantidad) {
    lbl.textContent = `Cantidad (${u})`;
    input.placeholder = `Ej: 1.500`;
    input.step = '0.001';
  } else {
    lbl.textContent = 'Importe ($)';
    input.placeholder = 'Ej: 2000';
    input.step = '0.01';
  }
}

function cerrarModalPeso() {
  const m = $('modal-peso');
  m.classList.add('hidden');
  m.classList.remove('flex');
  productoPesoActual = null;
}

/** Agrega (o acumula) una línea de producto por peso usando el modo elegido. */
function agregarPeso(mode) {
  if (!productoPesoActual) return;
  const p = productoPesoActual;
  const valor = Number(($('peso-valor').value || '').replace(',', '.'));

  // Toda validación fallida pasa `focoDestino: 'peso-valor'`: al cerrar la
  // alerta, el foco vuelve al input del modal (seleccionado) para que el cajero
  // corrija el número de inmediato. Resuelve el bug "no puedo escribir tras la
  // alerta": el clic en "Agregar" había dejado el foco en el botón, no en el
  // input, y el toast no se lo devolvía.
  const FOCO_VALOR = { focoDestino: 'peso-valor' };

  if (!valor || valor <= 0) {
    mostrarAlerta('Ingresa un valor mayor a cero.', 'error', FOCO_VALOR);
    return;
  }

    // stock disponible en la unidad continua (kg/m/L) — aprox. al derivar importe
  const disponible = Number(p.stock || 0);
  const u = etiquetaUnidadContinua(p);
  const modoModo = mode; // 'cantidad' (kg/m/L) | 'importe' ($)
  if (modoModo === 'cantidad' && valor > disponible) {
    mostrarAlerta(`Stock insuficiente: máximo disponible ${disponible} ${u}.`, 'warn', FOCO_VALOR);
    return;
  }
  // validación de alcance: importe no puede superar valor unitario del stock disponible
  if (modoModo === 'importe') {
    const maxImporte = disponible * Number(p.precio || 0);
    if (valor > maxImporte) {
      mostrarAlerta(`El importe excede el valor del stock disponible (≈ ${money(maxImporte)}).`, 'error', FOCO_VALOR);
      return;
    }
  }

  // Reutilizar línea existente del producto SOLO si el modo coincide (backend
  // rechaza productos repetidos en una misma venta → una línea por producto).
  const idx = carrito.findIndex((l) => l.producto.id === p.id);
  if (idx >= 0) {
    const act = carrito[idx];
    if (act.modo !== modoModo) {
      mostrarAlerta(`Este producto ya tiene una línea por ${act.modo === 'importe' ? 'importe ($)' : 'kilos (kg)'}. Quita la línea para cambiar el modo.`, 'warn');
      cerrarModalPeso();
      return;
    }
    if (modoModo === 'cantidad') {
      act.cantidad = Number(act.cantidad) + valor;
    } else {
      act.importe = Number(act.importe || 0) + valor;
    }
  } else {
    const linea = { producto: p, modo: modoModo };
    if (modoModo === 'cantidad') linea.cantidad = valor;
    else linea.importe = valor;
    carrito.push(linea);
  }

    cerrarModalPeso();
  renderCarrito();
}

// ---- SERVICIOS (librería: copia/impresión) ----

/** Producto de servicio que se está configurando en el modal. */
let productoServicioActual = null;

/**
 * Abre el modal de servicio/copia. Precarga las variantes de impresión
 * definidas en el inventario del producto (tipo_papel, color_bn) y deja el
 * foco en el input de cantidad para tipeo rápido (requisito del POS).
 */
function abrirModalServicio(p) {
  productoServicioActual = p;
  $('servicio-modal-titulo').textContent = p.nombre;
  const stockTxt = Number(p.stock || 0) > 0 ? `stock: ${formatearStock(p.stock, p.tipo_unidad)}` : 'ilimitado';
  $('servicio-modal-precio').textContent = `${money(p.precio)} / copia   ·   ${stockTxt}`;
  $('servicio-cantidad').value = '1';
  // Variantes por defecto del producto (fallback a los primeros del select).
  const papel = $('servicio-papel');
  if (papel) papel.value = p.tipo_papel || 'A4';
  const bn = $('servicio-bn');
  if (bn) bn.value = p.color_bn || 'B/N';

  const m = $('modal-servicio');
  m.classList.remove('hidden');
  m.classList.add('flex');
  // Auto-focus + select tras el reflow (mismo helper que el modal de peso).
  focusInputDiferido('servicio-cantidad', { seleccionar: true });
}

function cerrarModalServicio() {
  const m = $('modal-servicio');
  if (m) { m.classList.add('hidden'); m.classList.remove('flex'); }
  productoServicioActual = null;
}

/** Agrega (o acumula) una línea de servicio/copia al carrito. */
function agregarServicio() {
  if (!productoServicioActual) return;
  const p = productoServicioActual;
  const cantidad = Math.floor(Number(($('servicio-cantidad').value || '').replace(',', '.')));
  const FOCO = { focoDestino: 'servicio-cantidad' };

  if (!cantidad || cantidad <= 0) {
    mostrarAlerta('Ingresá una cantidad de copias mayor a cero.', 'error', FOCO);
    return;
  }
  // Tope de stock SOLO si el producto lo controla (stock > 0).
  const disponible = Number(p.stock || 0);
  if (disponible > 0 && cantidad > disponible) {
    mostrarAlerta(`Stock insuficiente: máximo ${formatearStock(disponible, p.tipo_unidad)} copias.`, 'warn', FOCO);
    return;
  }

  // Variantes elegidas en esta venta (ajustables aunque el producto traiga un default).
  const variante = {
    tipo_papel: $('servicio-papel')?.value || null,
    color_bn: $('servicio-bn')?.value || null,
  };

  // Una línea por producto (el backend rechaza productos repetidos). Si ya
  // existe, acumula la cantidad y actualiza la variante elegida.
  const idx = carrito.findIndex((l) => l.producto.id === p.id);
  if (idx >= 0) {
    const act = carrito[idx];
    const nueva = (Number(act.cantidad) || 0) + cantidad;
    if (disponible > 0 && nueva > disponible) {
      mostrarAlerta(`Stock insuficiente: máximo ${formatearStock(disponible, p.tipo_unidad)} copias.`, 'warn', FOCO);
      return;
    }
    act.cantidad = nueva;
    act.variante = variante;
  } else {
    carrito.push({ producto: p, modo: 'servicio', cantidad, variante });
  }

  cerrarModalServicio();
  renderCarrito();
}

// ---- Carrito ----
function quitarDelCarrito(id) {
  carrito = carrito.filter((i) => i.producto.id !== id);
  renderCarrito();
}

function renderCarrito() {
  const cont = $('carrito-items');
  cont.innerHTML = '';

  if (!carrito.length) {
    cont.innerHTML = '<div class="vacio"><svg class="h-9 w-9 opacity-60" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="9" cy="20" r="1"/><circle cx="18" cy="20" r="1"/><path d="M3 4h2l2.4 11.2a2 2 0 0 0 2 1.6h7.7a2 2 0 0 0 2-1.5L21 8H6"/></svg><p class="font-semibold text-pos-text-head">El carrito está vacío</p><p>Escaneá un código o tocá un producto para empezar.</p></div>';
    $('carrito-subtotal').textContent = money(0);
    $('carrito-descuentos').textContent = '-$0.00';
    $('carrito-total').textContent = money(0);
    actualizarEncabezadoCarrito();
    return;
  }

  let subtotal = 0;
  carrito.forEach((linea) => {
    const { producto } = linea;
    const importe = importeLinea(linea);
    subtotal += importe;

    const detalle = detalleLinea(linea);

    const row = document.createElement('div');
    row.className = 'flex items-center gap-3 py-3 border-b border-pos-secondary/50 last:border-0';
    const conStepper = linea.modo === 'unidad' || linea.modo === 'porcion';
    const stepper = conStepper
      ? `<div class="flex items-center shrink-0 rounded-xl border border-pos-secondary/80">
          <button type="button" data-menos="${producto.id}" class="icon-btn !h-9 !w-9" aria-label="Quitar una unidad de ${esc(producto.nombre)}"><svg fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14"/></svg></button>
          <span class="min-w-[1.75rem] text-center text-base font-semibold text-pos-text-head">${esc(linea.cantidad)}</span>
          <button type="button" data-mas="${producto.id}" class="icon-btn !h-9 !w-9" aria-label="Agregar una unidad de ${esc(producto.nombre)}"><svg fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 5v14M5 12h14"/></svg></button>
        </div>`
      : '';
    row.innerHTML = `
      <div class="min-w-0 flex-1">
        <p class="text-base font-medium text-pos-text-head truncate">${esc(producto.nombre)}</p>
        <p class="text-sm text-pos-text-body/70 truncate">${esc(detalle)}</p>
      </div>
      ${stepper}
      <span class="shrink-0 min-w-[4.5rem] text-right text-base font-semibold text-pos-text-head">${money(importe)}</span>
      <button data-quitar="${producto.id}" class="icon-btn !h-9 !w-9 shrink-0 text-pos-danger hover:!bg-pos-danger/10" aria-label="Quitar ${esc(producto.nombre)}">
        <svg fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
      </button>`;
    cont.appendChild(row);
  });

  $('carrito-subtotal').textContent = money(subtotal);
  $('carrito-descuentos').textContent = '-$0.00';
  $('carrito-total').textContent = money(subtotal);

  cont.querySelectorAll('[data-quitar]').forEach((btn) =>
    btn.addEventListener('click', () => quitarDelCarrito(btn.dataset.quitar))
  );
  cont.querySelectorAll('[data-menos], [data-mas]').forEach((btn) =>
    btn.addEventListener('click', () => {
      const id = btn.dataset.menos ?? btn.dataset.mas;
      const linea = carrito.find((l) => String(l.producto.id) === String(id));
      if (linea) agregarUnidad(linea.producto, btn.dataset.mas !== undefined ? 1 : -1);
    })
  );
  actualizarEncabezadoCarrito();

  actualizarVuelto();
}

/** Contador de ítems y botón "Vaciar" del encabezado del carrito. */
function actualizarEncabezadoCarrito() {
  const n = carrito.length;
  const contador = $('carrito-contador');
  if (contador) {
    contador.textContent = String(n);
    contador.classList.toggle('hidden', n === 0);
  }
  $('btn-vaciar-carrito')?.classList.toggle('hidden', n === 0);
}

/** Texto descriptivo de la línea según su modo. */
function detalleLinea(linea) {
  const p = linea.producto;
  const precioU = money(p.precio);
  if (linea.modo === 'importe') {
    const kg = cantidadLinea(linea).toFixed(3).replace(/\.?0+$/, '');
    return `${precioU}/kg · por importe → ≈ ${kg} kg`;
  }
  if (linea.modo === 'servicio') {
    const v = linea.variante || {};
    const extra = [v.tipo_papel, v.color_bn].filter(Boolean).join(' · ');
    return `${precioU}/copia × ${linea.cantidad} copia(s)${extra ? ' · ' + extra : ''}`;
  }
  if (esPorPeso(p)) {
    return `${precioU}/${etiquetaUnidadContinua(p)} × ${linea.cantidad} ${etiquetaUnidadContinua(p)}`;
  }
  return `${precioU} × ${linea.cantidad} ${p.tipo_unidad === 'porcion' ? 'porción(es)' : 'un.'}`;
}

// ---------- Cobro contra el backend local ----------
// La UI de alertas (`mostrarAlerta`) y el manejo de foco viven en `ui.js`
// (Single Source of Truth compartido con el resto de las vistas). Aquí sólo se
// reutiliza; los mensajes del dominio POS pasan `focoDestino` cuando procede.

/**
 * Traducción de errores del backend a contexto puntual del POS.
 */
function mensajeErrorVenta(err) {
  const msg = (err && err.message) || '';
  const lower = msg.toLowerCase();
  // Caja obligatoria: el backend devuelve 400/409 con este aviso.
  if (lower.includes('caja abierta') || lower.includes('caja abierta') || lower.includes('abre la caja')) {
    return {
      gravedad: 'caja',
      texto: 'Es obligatorio abrir la caja antes de registrar cobros. Abrí la caja (Control de Caja) y volvé a intentarlo.',
    };
  }
  return { gravedad: 'error', texto: msg || 'No se pudo registrar la venta.' };
}

async function cobrar() {
  if (!carrito.length) {
    mostrarAlerta('El carrito está vacío', 'error');
    return;
  }

  const metodoPago = $('metodo-pago').value;

  // Confirma método de pago elegido para el post. CC requiere cliente.
  let cliente = $('cliente-venta').value.trim() || 'Mostrador';
  let clienteId = null;

  if (metodoPago === 'cuenta_corriente') {
    const sel = $('select-cliente-cc');
    if (sel && sel.value) {
      clienteId = Number(sel.value);
      const csel = clientesCC.find((x) => x.id === clienteId);
      cliente = csel ? csel.nombre : cliente;
    } else {
      mostrarAlerta('Seleccioná un cliente para venta a cuenta corriente.', 'error');
      return;
    }
  }

    // Construir items según esquema VentaItem: EXACTAMENTE cantidad O importe.
  // Nota: la variante de impresión (papel/BN) del servicio es informativa para
  // el ticket y NO se envía al backend (el precio del servicio ya la contempla);
  // así evitamos persistir un dato cosmético (YAGNI aplicado al modelo).
  const items = carrito.map((linea) => {
    const base = { producto_id: linea.producto.id, descuento: 0 };
    if (linea.modo === 'importe') {
      return { ...base, importe: Number(linea.importe).toFixed(2) };
    }
    return { ...base, cantidad: Number(linea.cantidad).toFixed(3) };
  });

  const btn = $('btn-cobrar');
  btn.disabled = true;
  btn.textContent = 'Procesando...';

    const payload = { items, metodo_pago: metodoPago, cliente };
  if (clienteId !== null) payload.cliente_id = clienteId;

  const total = carrito.reduce((acc, l) => acc + importeLinea(l), 0);

  // VALIDACIÓN ESTRICTA DEL MONTO (defensa en profundidad: el backend también
  // valida). En efectivo, el monto abonado debe ser > 0 y >= total. Bloqueamos
  // la petición al servidor y avisamos con un toast ANTES de construir el
  // payload, evitando un viaje de red inútil y el descuadre de caja.
  if (metodoPago === 'efectivo') {
    const pagaConStr = $('paga-con').value;
    const montoAbonado = Number(pagaConStr);
    if (!pagaConStr || !Number.isFinite(montoAbonado) || montoAbonado < total) {
      btn.disabled = false;
      btn.textContent = 'Cobrar venta';
      mostrarAlerta('El monto ingresado no puede ser menor al total a pagar', 'error');
      return;
    }
    payload.paga_con = montoAbonado;
    payload.vuelto = Math.max(0, montoAbonado - total);
  }

  try {

    const venta = await api.registerSale(payload);
    // Éxito: NO limpiamos el POS instantáneamente. Se abre el modal
    // "Venta Completada" para que el cajero elija "Nueva Venta" o
    // "Imprimir Comprobante". El carrito se conserva hasta que decida.
    ventaUltima = { venta, items, metodoPago, cliente, total };
    abrirModalVentaCompletada(venta);
    // SINCRONIZACIÓN DE STOCK: la venta descontó inventario en la BD. Refresca
    // el catálogo desde el backend para que la UI refleje el stock REAL (evita
    // que una tarjeta muestre stock viejo o no se marque "Agotado" tras agotarse).
    // No bloquea el flujo: si falla, la venta ya está registrada y solo se avisa.
    try {
      await cargarProductos();
    } catch (e) {
      console.warn('No se pudo refrescar el catálogo tras la venta:', e?.message || e);
    }
  } catch (e) {
    const { gravedad, texto } = mensajeErrorVenta(e);
    if (gravedad === 'caja') {

      const b = $('error-caja-sin-abrir');
      if (b) b.classList.remove('hidden');
    }
    mostrarAlerta(texto, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Cobrar venta';
  }
}

// ===================== MODAL "VENTA COMPLETADA" =====================
/**
 * Abre el modal post-cobro. NO limpia el carrito: el cajero decide.
 * @param {Object} venta  Respuesta de api.registerSale (incluye folio).
 */
function abrirModalVentaCompletada(venta) {
  const folio = (venta && (venta.folio || venta.id)) || '—';
  $('vc-folio').textContent = folio;
  const m = $('modal-venta-completada');
  m.classList.remove('hidden');
  m.classList.add('flex');
  // Foco al botón primario (Nueva Venta) para operar 100% con teclado.
  setTimeout(() => { $('btn-vc-nueva')?.focus(); }, 50);
}

function cerrarModalVentaCompletada() {
  const m = $('modal-venta-completada');
  if (m) { m.classList.add('hidden'); m.classList.remove('flex'); }
}

/** El enlace "+ Cliente" solo aparece con el campo plegado y fuera de cuenta corriente. */
function sincronizarClienteLibre() {
  const abierto = !$('cliente-venta')?.classList.contains('hidden');
  const esCC = $('metodo-pago')?.value === 'cuenta_corriente';
  $('btn-agregar-cliente')?.classList.toggle('hidden', abierto || esCC);
}

/** Cliente libre plegado: solo el enlace "+ Cliente" del encabezado. */
function plegarCliente() {
  $('cliente-venta')?.classList.add('hidden');
  sincronizarClienteLibre();
}

/** Despliega el campo de cliente y le da el foco. */
function desplegarCliente() {
  const campo = $('cliente-venta');
  campo?.classList.remove('hidden');
  sincronizarClienteLibre();
  campo?.focus();
}

/** Vacía los datos del cobro anterior: monto abonado, vuelto y cliente. */
function limpiarDatosDeCobro() {
  const pagaCon = $('paga-con');
  if (pagaCon) pagaCon.value = '';
  const clienteLibre = $('cliente-venta');
  if (clienteLibre) clienteLibre.value = '';
  plegarCliente();
  const clienteCC = $('select-cliente-cc');
  if (clienteCC) clienteCC.value = '';
  actualizarVuelto();
}

/** Limpia el POS para una nueva venta: carrito, buscador, cobro y foco. */
function reiniciarPOS() {
  carrito = [];
  renderCarrito();
  const search = $('pos-search');
  if (search) { search.value = ''; onSearch(''); }
  limpiarDatosDeCobro();
  cerrarModalVentaCompletada();
  // El foco SIEMPRE vuelve al buscador (continuidad del escaneo).
  setTimeout(() => search?.focus(), 50);
}

/**
 * Vacía el carrito en frío (atajo Ctrl+Delete). Pide confirmación porque es
 * una acción destructiva con riesgo de pérdida de trabajo del cajero.
 * Si el carrito está vacío, no hace nada.
 */
function vaciarCarrito() {
  if (!carrito.length) {
    mostrarAlerta('El carrito ya está vacío', 'warn');
    return;
  }
  const ok = window.confirm('¿Vaciar todo el carrito? Se quitarán los productos cargados.');
  if (!ok) return;
  carrito = [];
  renderCarrito();
  limpiarDatosDeCobro();
  mostrarAlerta('Carrito vaciado', 'ok');
}

/**
 * Construye el HTML del comprobante de venta en el contenedor #area-impresion
 * (mismo patrón verificado que el ticket de cierre de caja: `.ticket` + la
 * regla @media print global) y dispara window.print().
 */
function imprimirComprobanteVenta() {
  const snap = ventaUltima;
  if (!snap) return;
  const { venta, items, metodoPago, cliente, total } = snap;

  // Enlaza cada item enviado con su producto para reconstruir nombre/detalle.
  const filas = items.map((it, i) => {
    const linea = carrito[i] || null;
    const prod = linea?.producto || {};
    const nombre = prod.nombre || `Producto #${it.producto_id}`;
    const detalle = linea ? detalleLinea(linea) : '';
    const imp = linea ? importeLinea(linea) : 0;
    return `<tr>
      <td class="t-izq">${esc(nombre)}${detalle ? `<br><span class="t-muted">${esc(detalle)}</span>` : ''}</td>
      <td class="t-der">${money(imp)}</td>
    </tr>`;
  }).join('');

  const fecha = new Date().toLocaleString('es-CL');
  const folio = venta?.folio || venta?.id || '—';
  const metodoTxt = ({
    efectivo: 'Efectivo', tarjeta: 'Tarjeta', transferencia: 'Transferencia',
    mixto: 'Mixto', cuenta_corriente: 'Cuenta Corriente',
  })[metodoPago] || metodoPago;

  // Encabezado del negocio: nombre centrado (configurado en Configuración).
  // Solo se imprime si hay un nombre cargado; sin él, la línea no se renderiza
  // (sin espacio residual ni marca del software).
  const negocioNombre = (window.NEGOCIO_NOMBRE || '').trim();
  const lineaNegocio = negocioNombre
    ? `<div class="t-center t-neg">${esc(negocioNombre)}</div>`
    : '';

  const html = `
    <div class="ticket">
      ${lineaNegocio}
      <div class="t-center t-neg">COMPROBANTE DE VENTA</div>
      <div class="t-sep">${'='.repeat(32)}</div>
      <div class="t-izq">Folio: <span class="t-neg">${folio}</span></div>
      <div class="t-izq">Fecha: ${fecha}</div>
      <div class="t-izq">Cliente: ${esc(cliente || 'Mostrador')}</div>
      <div class="t-izq">Pago: ${metodoTxt}</div>
      <div class="t-sep">${'-'.repeat(32)}</div>
      <table class="tb-detalle">${filas}</table>
      <div class="t-sep">${'-'.repeat(32)}</div>
      <table class="tb-total">
        <tr><td class="t-neg">TOTAL</td><td class="t-der t-neg">${money(total)}</td></tr>
      </table>
      <div class="t-sep">${'='.repeat(32)}</div>
      <div class="t-center t-muted">¡Gracias por su compra!</div>
    </div>`;

  const area = $('area-impresion');
  if (!area) return;
  area.innerHTML = html;
  window.print();
  // Limpieza tras el diálogo de impresión (no deja residuos en el DOM).
  area.innerHTML = '';
}

// ===================== CUENTA CORRIENTE =====================
/** Alterna bloques "cliente libre" vs "selector CC" según el método de pago. */
function toggleMetodoPago() {
  const metodo = $('metodo-pago').value;
  const esCC = metodo === 'cuenta_corriente';
  const esEfectivo = metodo === 'efectivo';
  
  $('bloque-cliente-libre').classList.toggle('hidden', esCC);
  $('bloque-cliente-cc').classList.toggle('hidden', !esCC);
  $('bloque-vuelto').classList.toggle('hidden', !esEfectivo);
  $('fila-vuelto')?.classList.toggle('hidden', !esEfectivo);
  sincronizarClienteLibre();
  
  if (esCC) poblarSelectClienteCC();
  if (esEfectivo) actualizarVuelto();
}

function actualizarVuelto() {
    const total = carrito.reduce((acc, l) => acc + importeLinea(l), 0);
    const pagaCon = Number($('paga-con').value) || 0;
    const vuelto = Math.max(0, pagaCon - total);
    $('vuelto-monto').textContent = money(vuelto);
}

/** Carga y rellena el select de clientes activos (con su saldo). */
async function poblarSelectClienteCC() {
  const sel = $('select-cliente-cc');
  const previo = sel.value;
  try {
    const arr = await api.getClients(false);
    clientesCC = Array.isArray(arr) ? arr : [];
    if (clientesCC.length) {
      sel.innerHTML =
        '<option value="">Seleccioná un cliente…</option>' +
        clientesCC
          .map((c) => {
            const saldo = Number(c.saldo_deuda || 0);
            const etiqueta = saldo > 0 ? `${c.nombre} (debe ${money(saldo)})` : c.nombre;
            return `<option value="${esc(c.id)}">${esc(etiqueta)}</option>`;
          })
          .join('');
    } else {
      sel.innerHTML = '<option value="">No hay clientes registrados</option>';
    }
    if ([...sel.options].some((o) => String(o.value) === String(previo))) {
      sel.value = previo;
    }
    sel.disabled = false;
  } catch (e) {
    sel.innerHTML = '<option value="">Error al cargar clientes</option>';
  }
}

function abrirModalNuevoCliente() {
  $('cliente-nuevo-nombre').value = '';
  $('cliente-nuevo-tel').value = '';
  $('modal-nuevo-cliente').classList.remove('hidden');
  $('modal-nuevo-cliente').classList.add('flex');
  // Mismo patrón que el modal de peso: foco fiable tras el reflow.
  focusInputDiferido('cliente-nuevo-nombre', { seleccionar: false });
}

function cerrarModalNuevoCliente() {
  const m = $('modal-nuevo-cliente');
  if (m) { m.classList.add('hidden'); m.classList.remove('flex'); }
}

async function guardarClienteNuevo() {
  const nombre = ($('cliente-nuevo-nombre').value || '').trim();
  if (!nombre) {
    mostrarAlerta('El nombre del cliente es obligatorio', 'error');
    return;
  }
  try {
    const cliente = await api.createClient({
      nombre,
      telefono: ($('cliente-nuevo-tel').value || '').trim() || null,
    });
    clientesCC = [...clientesCC, cliente];
    cerrarModalNuevoCliente();
    // Selecciona el cliente recién creado y re-renderiza.
    await poblarSelectClienteCC();
    $('select-cliente-cc').value = String(cliente.id);
    mostrarAlerta(`Cliente "${cliente.nombre}" registrado`, 'ok');
  } catch (e) {
    mostrarAlerta(`No se pudo registrar el cliente: ${e.message}`, 'error');
  }
}

/** ¿El usuario de la sesión es administrador? */
function esAdminSesion() {
  try {
    return JSON.parse(localStorage.getItem('user') || 'null')?.rol === 'admin';
  } catch {
    return false;
  }
}

/**
 * Resuelve un código leído (lector global o buscador): catálogo local primero,
 * backend como respaldo. Si no existe, el admin recibe un acceso directo para
 * crear el producto con ese código; el cajero solo ve el aviso.
 */
async function procesarCodigoEscaneado(crudo) {
  const codigo = normalizarCodigo(crudo);
  if (!codigo) return;
  const minusc = codigo.toLowerCase();
  let producto = catalogoCompleto.find(
    (p) => p.codigo_barras && p.codigo_barras.toLowerCase() === minusc
  );
  if (!producto) {
    try {
      producto = await api.getByBarcode(codigo);
    } catch (e) {
      producto = null;
    }
  }
  if (!producto) {
    mostrarAlerta(`El código ${codigo} no está cargado.`, 'warn', {
      duracionMs: 9000,
      accion: esAdminSesion()
        ? { texto: 'Crear producto con este código', href: `inventario.html?nuevo=${encodeURIComponent(codigo)}` }
        : null,
    });
    return;
  }
  onSelectProducto(producto);
}

/** -- Buscador / escáner de código de barras ----------
 * Enter: si la búsqueda escrita dejó UNA única coincidencia la agrega al
 * carrito (flujo rápido). Si además coincide EXACTO con un código de barras,
 * se agrega ése (pistola USB/BT). Se limpia el input manteniendo el foco.
 */
function escanear(ev) {
  const input = $('pos-search');
  const texto = (input.value || '').trim();
  if (!texto) {
    onSearch('');
    input.focus();
    return;
  }

  // 1) Barcode exacto (comportamiento nativo del lector láser: envía el código
  //    completo seguido de Enter). Coincidencia EXACTA ⇒ alta inmediata.
  const porBarcode = catalogoCompleto.find(
    (p) => p.codigo_barras && p.codigo_barras.toLowerCase() === texto.toLowerCase()
  );
  if (porBarcode) {
    onSelectProducto(porBarcode);
    input.value = '';
    input.focus();
    return;
  }

  // 2) Búsqueda textual: si deja exactamente UNA coincidencia, la agrega.
  const q = texto.toLowerCase();
  const coinciden = catalogoCompleto.filter(
    (p) =>
      (p.nombre && p.nombre.toLowerCase().includes(q)) ||
      (p.codigo_barras && p.codigo_barras.toLowerCase().includes(q))
  );
  if (coinciden.length === 1) {
    onSelectProducto(coinciden[0]);
    input.value = '';
    input.focus();
    return;
  }
  if (coinciden.length === 0) {
    // Si parece un código (una sola palabra, 4+ caracteres) se consulta el
    // backend por si el catálogo local quedó desactualizado.
    if (/^\S{4,}$/.test(texto)) {
      procesarCodigoEscaneado(texto);
    } else {
      mostrarAlerta('Producto no encontrado', 'error');
    }
    input.value = '';
    onSearch('');
    // El foco se restituye también tras el auto-cierre de la alerta.
    input.focus();
    return;
  }
  // Varias coincidencias: quedan listadas en la grilla; el input conserva el
  // texto para que el cajero refina. El foco NO se abandona (evita el limbo).
  input.focus();
}


// ---- Inicialización bajo guardia ----
/** Filtro de búsqueda sobre el catálogo COMPLETO (no sobre el filtro previo). */
function onSearch(raw) {
  const q = (raw || '').trim().toLowerCase();

  // Búsqueda vacía ⇒ se vuelve a la lista completa original.
  if (!q) {
    renderCatalogo(catalogoCompleto, false);
    return;
  }

  const filtrados = catalogoCompleto.filter(
    (p) =>
      (p.nombre && p.nombre.toLowerCase().includes(q)) ||
      (p.codigo_barras && p.codigo_barras.toLowerCase().includes(q))
  );
  renderCatalogo(filtrados, true); // esFiltro=true → muestra "sin coincidencias"
}

/**
 * Recarga el catálogo COMPLETO desde el backend y lo re-renderiza.
 *
 * Se usa en dos momentos (DRY, una única fuente de verdad):
 *   1. Al inicializar el terminal.
 *   2. DESPUÉS de cada cobro exitoso — el stock de la BD cambió y la UI debe
 *      reflejarlo de inmediato (antes mostraba stock viejo; p.ej. "12" cuando
 *      la DB ya tenía "2"). Sin este re-fetch la tarjeta quedaba desincronizada
 *      y el badge "Agotado" / el bloqueo por stock<=0 no se activaban a tiempo.
 *
 * Mantiene la búsqueda activa: si hay texto en el buscador, re-aplica el filtro
 * sobre los datos frescos en lugar de mostrar el catálogo entero.
 */
async function cargarProductos() {
  const productos = await api.getProducts();
  catalogoCompleto = productos || [];
  // Re-respeta el filtro de búsqueda vigente (si lo hay) sobre datos frescos.
  const q = ($('pos-search')?.value || '').trim().toLowerCase();
  if (q) {
    onSearch(q);
  } else {
    renderCatalogo(catalogoCompleto, false);
  }
}

async function init() {
  if (window.authGuardReady) {
    await window.authGuardReady;
  }

  // Fachada global (compat): expone mostrarAlerta/restaurarFocoSiLibre en window
  // para scripts no-módulo. Idempotente y provisto por ui.js (Single Source).
  exponerUIglobal();

  $('btn-cobrar').addEventListener('click', cobrar);

  // Atajos de teclado (F1 buscar, F2 cobrar, F4 nueva venta, F8 imprimir,
  // Esc cerrar modal, Ctrl+Del vaciar). Ver services/atajos.js.
  instalarAtajosPOS();
  // Ctrl+Del (atajos.js) emite este evento para no duplicar la lógica de
  // vaciado (Single Source of Truth: pos.js es el dueño del estado `carrito`).
  window.addEventListener('pos-vaciar-carrito', vaciarCarrito);

  // Modal "Venta Completada": Nueva Venta (limpia) / Imprimir (ticket + limpia).
  $('btn-vc-nueva').addEventListener('click', reiniciarPOS);
  $('btn-vc-imprimir').addEventListener('click', () => {
    imprimirComprobanteVenta();
    // Tras imprimir, se limpia el POS para la siguiente venta.
    reiniciarPOS();
  });

  // Modal de peso
  $('peso-modo-cantidad').addEventListener('change', () => {
    actualizarPlaceholder();
    // El clic en el radio roba el foco al input; lo devolvemos explícitamente
    // para que el teclado numérico siga respondiendo sin re-tocar.
    focusInputDiferido('peso-valor', { seleccionar: true });
  });
  $('peso-modo-importe').addEventListener('change', () => {
    actualizarPlaceholder();
    focusInputDiferido('peso-valor', { seleccionar: true });
  });
  $('btn-peso-agregar').addEventListener('click', () => {
    const mode = $('peso-modo-importe').checked ? 'importe' : 'cantidad';
    agregarPeso(mode);
  });
    $('btn-peso-cancelar').addEventListener('click', cerrarModalPeso);
  const btnCancel2 = $('btn-peso-cancelar-2');
  if (btnCancel2) btnCancel2.addEventListener('click', cerrarModalPeso);

  // Modal de SERVICIO (librería: copia/impresión).
  $('btn-servicio-agregar')?.addEventListener('click', agregarServicio);
  $('btn-servicio-cancelar')?.addEventListener('click', cerrarModalServicio);
  const btnServCancel2 = $('btn-servicio-cancelar-2');
  if (btnServCancel2) btnServCancel2.addEventListener('click', cerrarModalServicio);
  // Enter en la cantidad del servicio = confirmar (ergonomía de teclado).
  const servicioInput = $('servicio-cantidad');
  if (servicioInput) {
    servicioInput.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter') return;
      e.preventDefault();
      agregarServicio();
    });
  }

  // Escáner / barcode: Enter simula el disparo de la pistola.
  // El listener está ACOTADO al input #pos-search (no es global), y sólo
  // intercepta Enter. Aun así, si hay un modal abierto NO debe secuestrar el
  // evento: la escritura nativa y el Enter del modal deben tener prioridad.
  // Lector USB/Bluetooth: funciona aunque el foco no esté en el buscador.
  instalarLector(procesarCodigoEscaneado);

  const search = $('pos-search');
  search.addEventListener('input', (e) => onSearch(e.target.value));
  search.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    if (modalActivo()) return; // guard clause: nunca interferir con un modal
    e.preventDefault();
    escanear(e);
  });

  // Enter dentro del input de peso = confirmar y agregar (ergonomía de teclado).
  const pesoInput = $('peso-valor');
  if (pesoInput) {
    pesoInput.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter') return;
      e.preventDefault();
      const mode = $('peso-modo-importe').checked ? 'importe' : 'cantidad';
      agregarPeso(mode);
    });
  }

  // Banner "abrir caja" cerrable, con acceso directo a Caja.
  const errorCaja = $('error-caja-sin-abrir');
  if (errorCaja) {
    const cerrar = errorCaja.querySelector('[data-close-error]');
    if (cerrar) cerrar.addEventListener('click', () => errorCaja.classList.add('hidden'));
  }

  const metodoPago = $('metodo-pago');
  if (metodoPago) {
    metodoPago.addEventListener('change', toggleMetodoPago);
    // Estado inicial según método por defecto (efectivo).
    toggleMetodoPago();
  }
  $('btn-agregar-cliente')?.addEventListener('click', desplegarCliente);
  $('btn-vaciar-carrito')?.addEventListener('click', vaciarCarrito);
  const inputPagaCon = $('paga-con');
  if (inputPagaCon) {
      inputPagaCon.addEventListener('input', actualizarVuelto);
  }
  const btnNuevoCC = $('btn-nuevo-cliente-cc');
  if (btnNuevoCC) btnNuevoCC.addEventListener('click', abrirModalNuevoCliente);
  const btnGuardarCli = $('btn-cliente-guardar');
  if (btnGuardarCli) btnGuardarCli.addEventListener('click', guardarClienteNuevo);
  const btnCanceCli = $('btn-cliente-cancelar');
  if (btnCanceCli) btnCanceCli.addEventListener('click', cerrarModalNuevoCliente);
  const btnCanceCli2 = $('btn-cliente-cancelar-2');
  if (btnCanceCli2) btnCanceCli2.addEventListener('click', cerrarModalNuevoCliente);

  try {
    await cargarProductos();
  } catch (e) {
    $('pos-catalogo').innerHTML = `<p class="col-span-full text-center text-pos-danger py-8">No se pudieron cargar los productos: ${esc(e.message)}</p>`;
  }
}

init();

