---
name: Vortex Apex POS
description: Punto de venta de escritorio, sobrio y premium; rail blanco (claro) o carbón (oscuro) con ítem activo violeta y títulos en tipografía extendida.
colors:
  violeta-apex: "#6246ea"
  violeta-apex-oscuro-brand: "#7059f0"
  violeta-claro: "#a898ff"
  carbon-rail: "#21222e"
  carbon-rail-oscuro: "#1e1f2b"
  carbon-logo: "#2b2c34"
  rail-texto: "#bebfd2"
  bruma-fondo: "#f3f3f9"
  tarjeta: "#ffffff"
  borde-neutro: "#e0e0ee"
  tinta-titulo: "#161622"
  tinta-cuerpo: "#343548"
  coral-peligro: "#cd343c"
  verde-exito: "#15803d"
  ambar-aviso: "#b45309"
  noche-fondo: "#0f1017"
  noche-tarjeta: "#191a25"
  noche-campo: "#13141d"
  noche-borde: "#303144"
  noche-titulo: "#f4f4fa"
  noche-cuerpo: "#c0c1d2"
  noche-peligro: "#f87171"
  noche-exito: "#4ade80"
  noche-aviso: "#fbbf24"
typography:
  marca:
    fontFamily: "Unbounded, Onest, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  titulo-pantalla:
    fontFamily: "Unbounded, Onest, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: 1.5
    letterSpacing: "-0.01em"
  titulo-modal:
    fontFamily: "Onest, ui-sans-serif, system-ui, Segoe UI, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: 1.55
  cuerpo:
    fontFamily: "Onest, ui-sans-serif, system-ui, Segoe UI, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
  etiqueta:
    fontFamily: "Onest, ui-sans-serif, system-ui, Segoe UI, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.33
  encabezado-tabla:
    fontFamily: "Onest, ui-sans-serif, system-ui, Segoe UI, sans-serif"
    fontSize: "0.7rem"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "0.06em"
rounded:
  foco: "6px"
  control: "12px"
  superficie: "16px"
  pastilla: "9999px"
spacing:
  control-y: "10px"
  control-x: "16px"
  celda-x: "16px"
  celda-y: "12px"
  hueco-formulario: "16px"
  rail-ancho: "256px"
components:
  btn-primary:
    backgroundColor: "{colors.violeta-apex}"
    textColor: "{colors.tarjeta}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
    typography: "{typography.cuerpo}"
  btn-secondary:
    backgroundColor: "{colors.tarjeta}"
    textColor: "{colors.tinta-titulo}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  btn-danger:
    backgroundColor: "{colors.coral-peligro}"
    textColor: "{colors.tarjeta}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  pos-card:
    backgroundColor: "{colors.tarjeta}"
    rounded: "{rounded.superficie}"
  pos-modal:
    backgroundColor: "{colors.tarjeta}"
    rounded: "{rounded.superficie}"
  form-input:
    backgroundColor: "{colors.tarjeta}"
    textColor: "{colors.tinta-titulo}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
  badge-primary:
    textColor: "{colors.violeta-apex}"
    rounded: "{rounded.pastilla}"
    padding: "2px 10px"
  rail:
    backgroundColor: "{colors.carbon-rail}"
    textColor: "{colors.rail-texto}"
    width: "{spacing.rail-ancho}"
  rail-link:
    textColor: "{colors.rail-texto}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
  rail-link-active:
    textColor: "#ffffff"
    rounded: "{rounded.control}"
---

# Design System: Vortex Apex POS

## Overview

**Creative North Star: "El Mostrador Carbón"**

Un mostrador de trabajo bien terminado: superficies calmas con un matiz violeta, texto legible durante ocho horas y una sola pieza con carácter, el rail de navegación carbón. Todo lo demás se retira para que el cobro sea rápido. La paleta nace del logo (violeta, carbón, un punto coral) y los neutros llevan un matiz violeta en lugar de grises puros.

El único gesto de marca es la combinación de dos cosas: el rail carbón con el ítem activo en violeta, y los títulos de pantalla en tipografía extendida (Unbounded), que hace eco del wordmark. Fuera de eso el sistema es deliberadamente sobrio: tarjetas planas con borde fino, un solo violeta de acento, color semántico solo para estado.

Funciona en claro y oscuro con los mismos nombres de token. El rail acompaña al tema: blanco en claro, carbón en oscuro; solo el panel de marca de las pantallas sin sesión es carbón siempre. Todo es local: fuentes e íconos viajan con la app, sin CDN.

**Key Characteristics:**
- Rail blanco en claro y carbón en oscuro; el violeta aparece en el ítem activo, el botón primario, el foco y el acento de texto.
- Títulos de pantalla en Unbounded; el resto en Onest con cifras tabulares.
- Tarjetas y modales con borde fino de 1px y sombra difusa, nunca sombra dura.
- Interfaz escalada a 14 px base (html al 87,5 %), todo en rem.
- Foco visible siempre; movimiento corto y respetuoso de `prefers-reduced-motion`.

## Colors

Paleta de un acento violeta sobre neutros teñidos de violeta, con el carbón del logo reservado al rail. Los tokens viven como canales RGB en variables `--pos-*` (`:root` claro, `.dark` oscuro); el frontmatter lista los valores en hex como referencia normativa.

### Primary
- **Violeta Apex** (#6246ea): acento y relleno sólido del botón primario, anillo de foco, texto de badge primario. En oscuro el texto de acento pasa a **Violeta Claro** (#a898ff) y el relleno del botón a #7059f0 para mantener contraste.

### Secondary
- **Carbón del Rail** (#21222e claro / #1e1f2b oscuro): fondo del rail y del panel de marca de las pantallas sin sesión. Texto del rail en #bebfd2. El carbón de logo (#2b2c34) es la referencia de marca y el trazo en tema claro.

### Tertiary (semánticos)
- **Coral Peligro** (#cd343c claro / #f87171 oscuro): coral del logo oscurecido para contraste AA. Errores, acción destructiva, badge de peligro.
- **Verde Éxito** (#15803d / #4ade80): cobro confirmado, notificaciones OK.
- **Ámbar Aviso** (#b45309 / #fbbf24): advertencias, stock bajo.

### Neutral
- **Bruma de Fondo** (#f3f3f9 / noche #0f1017): fondo de pantalla.
- **Tarjeta** (#ffffff / #191a25): tarjetas, modales y encabezado. Campo de formulario: blanco / #13141d.
- **Borde Neutro** (#e0e0ee / #303144): bordes, divisores y rellenos neutros.
- **Tinta de Título** (#161622 / #f4f4fa) y **Tinta de Cuerpo** (#343548 / #c0c1d2): texto.

### Named Rules
**The Rail Follows The Theme Rule.** El rail es blanco en claro y carbón en oscuro; el panel de marca de login es carbón en ambos temas.

**The One Violet Rule.** El violeta es el único acento cromático. Aparece en el ítem activo del rail, el botón primario, el foco, selección y badges primarios; los demás colores son semánticos y solo comunican estado.

**The Token Only Rule.** Ningún color se escribe a mano en una pantalla: se usan las utilidades `pos-*` para que el cambio de tema funcione sin tocar el HTML.

## Typography

**Display Font:** Unbounded (con Onest, ui-sans-serif, system-ui)
**Body Font:** Onest (con ui-sans-serif, system-ui, Segoe UI)

**Character:** Unbounded es ancha y firme, eco del wordmark; Onest es neutra, de lectura limpia y con cifras tabulares para precios y totales. Ambas son variables, locales (`assets/fonts/*.woff2`, licencia OFL) y cargan con `font-display: swap`.

### Hierarchy
- **Display / marca** (Unbounded 600, 1.875rem, interlineado ajustado): frase de bienvenida del panel de marca en pantallas sin sesión.
- **Headline** (Unbounded 600, 1.5rem): título de pantalla sin sesión (`h1` de login).
- **Title** (Unbounded 600, 1rem): título del encabezado de cada pantalla interna, p. ej. "Punto de Venta".
- **Modal title** (Onest 600, 1.125rem): títulos de modales.
- **Body** (Onest 400, 0.875rem): texto, celdas y controles. Base global 14 px.
- **Label** (Onest 600, 0.75rem): etiquetas de campo y badges.
- **Table head** (Onest 600, 0.7rem, 0.06em, mayúsculas): encabezados de tabla.

### Named Rules
**The Extended Voice Rule.** Unbounded se usa solo en títulos de pantalla y la frase de marca (clase `font-marca`); nunca en cuerpo, botones, datos ni cifras.

**The Tabular Figures Rule.** Las cifras son de ancho fijo en todo el cuerpo para que precios y totales se alineen.

## Layout

Aplicación de dos zonas: rail fijo a la izquierda (16rem; en pantallas menores a `lg` se oculta fuera de lienzo y se abre como panel con overlay) y área de trabajo con encabezado y contenido. El POS parte el área en catálogo y carrito (carrito de 24rem aprox.); la grilla de productos decide 2 a 6 columnas por el ancho real del contenedor (container queries), no por la ventana. Las pantallas sin sesión usan una rejilla 5fr/6fr con panel de marca carbón a la izquierda (solo desde 1024px) y tarjeta de formulario de hasta 26rem a la derecha.

El ritmo es compacto, pensado para ~1366×768: controles de 10px/16px, celdas de tabla 12px/16px, formularios con 16px entre campos. Los objetivos táctiles de los botones de icono son de 36px.

## Elevation & Depth

Híbrido: capas tonales (rail < fondo < tarjeta < campo) más sombras difusas y bajas. Nunca hay sombras duras desplazadas.

### Shadow Vocabulary
- **Tarjeta** (`0 1px 2px rgb(shadow / .05), 0 8px 24px -12px rgb(shadow / var(--pos-shadow-a))`): tarjetas, en dos capas; la sombra se tiñe de violeta en claro y es negra y más densa en oscuro.
- **Botón primario** (`inset 0 1px 0 rgb(255 255 255 / .18), 0 6px 14px -8px rgb(0 0 0 / .5)`): luz superior leve.
- **Modal** (`0 24px 60px -20px rgb(0 0 0 / .45)`): la mayor elevación del sistema.
- **Campo en foco** (`0 0 0 3px rgb(brand / .22)`): anillo, no sombra de profundidad.

### Named Rules
**The Soft Lift Rule.** La elevación es difusa y se sube un nivel solo para modales; las tarjetas de producto añaden una sombra de hover y subida de 2px, y nada más se levanta.

## Shapes

Esquinas generosas pero contenidas: 12px para controles (botones, campos, ítems del rail), 16px para superficies (tarjetas, modales), píldora completa para badges y 6px en el contorno de foco. Bordes de 1px en tono neutro con transparencia; el contorno de foco es de 2px violeta con 2px de separación.

## Components

### Buttons
- **Shape:** curvatura de control (12px), padding 10px 16px, texto 0.875rem semibold.
- **Primary (`btn-primary`):** relleno violeta Apex, texto blanco, luz superior inset. Hover sube el brillo (1.1), no la opacidad; al pulsar baja 1px.
- **Secondary (`btn-secondary`):** tarjeta con borde neutro y texto de título; hover rellena de neutro al 45 %.
- **Danger (`btn-danger`) y `btn-danger-quiet`:** el sólido queda para confirmar en el modal; en filas se usa el contorno discreto de coral con relleno suave al hover.
- **Disabled:** 50 % de opacidad y cursor no permitido.

### Cards / Containers (`pos-card`)
- **Corner Style:** 16px. **Background:** tarjeta. **Border:** 1px neutro al 70 %. **Shadow:** vocabulario Tarjeta.
- La tarjeta de producto (`producto-card`) sube 2px y enmarca el borde en violeta al 60 % al hover.

### Inputs / Fields (`form-input-pos`)
- **Style:** fondo de campo, borde neutro de 1px, 12px de radio, sombra interior mínima; etiqueta (`form-label`) 0.75rem semibold encima.
- **Hover:** borde de cuerpo al 35 %. **Focus:** borde violeta y anillo de 3px al 22 %. **Disabled:** 60 % de opacidad.

### Tables (`pos-table`)
Encabezado con fondo neutro al 30 %, texto pequeño en mayúsculas con 0.06em; filas de 12px/16px con divisor tenue y hover violeta al 5 %.

### Badges (`badge-*`)
Píldora con relleno al 14 % del color y texto en el mismo color: primary, danger, success, warning (16 %) y neutral.

### Modals (`pos-modal`)
Misma superficie que la tarjeta (16px, borde 1px) con la mayor elevación. Entrada `animate-pop-in` de 0.2s con escala 0.96 y subida de 6px.

### Navigation (Rail: `rail`, `rail-link`)
- **Style:** 16rem, blanco en claro (borde derecho 1px del color de bordes) y carbón en oscuro (borde blanco al 6 %); "Sesión" anclada al fondo; enlaces de 12px de radio con ícono SVG de 1.15rem y texto 0.875rem medio.
- **Hover:** relleno blanco al 6 % y texto blanco. **Activo (`aria-current="page"`):** relleno violeta al 22 %, anillo interior violeta al 35 %, texto blanco e ícono #a898ff. Este ítem es el gesto de marca.
- **Grupos:** `rail-titulo` pequeño, en mayúsculas, con 0.08em. **Salir (`rail-salir`):** rojo claro, con hover rojo tenue.
- **Móvil:** el rail se desliza fuera de lienzo y se abre sobre un overlay.

### Pantallas de acceso (`auth-*`)
Panel de marca carbón con una geometría lineal al 7 % de blanco como decoración, frase en Unbounded y lista de puntos con check violeta claro; a la derecha, tarjeta de formulario centrada.

### States
- **Foco:** contorno violeta de 2px, offset 2px, en todo lo interactivo; los campos usan su propio anillo.
- **Vacío (`vacio`):** centrado, texto de cuerpo al 75 %.
- **Selección:** violeta al 28 %.

### Motion
Transiciones de 0.12 a 0.15s en color, relleno y brillo; entradas de modal y aviso de 0.2 a 0.22s con curva `cubic-bezier(0.16, 1, 0.3, 1)`, sin rebote. Con `prefers-reduced-motion: reduce` toda animación y transición baja a 0.01ms.

## Do's and Don'ts

### Do:
- **Do** usar las utilidades `pos-*` y variables `--pos-*` para todo color, para que claro y oscuro funcionen sin editar el HTML.
- **Do** mantener el ítem activo del rail en violeta (10 % en claro, 22 % en oscuro) y `aria-current="page"`.
- **Do** poner los títulos de pantalla en Unbounded (`font-marca`) y todo lo demás en Onest.
- **Do** usar 12px de radio en controles y 16px en tarjetas y modales.
- **Do** verificar contraste AA en claro y oscuro y conservar el contorno de foco de 2px.
- **Do** usar íconos SVG locales; nada de CDN ni fuentes remotas.

### Don't:
- **Don't** usar un segundo color de acento; los colores semánticos son solo estado.
- **Don't** escribir colores en hex dentro de las pantallas ni usar grises puros: los neutros llevan matiz violeta.
- **Don't** usar Unbounded en cuerpo, botones, tablas ni cifras.
- **Don't** invertir el rail a claro en el tema claro.
- **Don't** usar sombras duras desplazadas ni animaciones con rebote.
- **Don't** depender de CDN, scripts en línea ni manejadores en línea (la CSP los bloquea).
