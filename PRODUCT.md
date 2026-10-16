# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Comercios chicos y medianos de varios rubros (quioscos, drugstores y otros), con una PC o notebook en el mostrador. El cajero cobra con lector de códigos y teclado durante jornadas de ~8 h; el dueño/administrador gestiona inventario, caja, cuentas corrientes, usuarios y mira reportes. Lo instala y licencia el proveedor (Ezequiel), presencial o por WhatsApp.

## Product Purpose
Vortex Apex es un punto de venta de escritorio que funciona 100 % sin internet (Electron + backend local con SQLite). Éxito: cobrar rápido y sin errores, cerrar la caja sin diferencias y que el dueño entienda su negocio de un vistazo.

## Positioning
POS local, sin nube ni abonos de servidor, con licencia mensual firmada y datos que nunca salen de la PC del cliente.

## Operating Context
Mostrador con poca luz o mucha luz de local, pantallas de notebook chicas (~1366×768), a veces táctiles; ventas con lector de código de barras y atajos de teclado; tickets impresos; claro y oscuro según el local.

## Capabilities and Constraints
Pantallas: login, asistente de alta, recuperación de contraseña, bloqueo por licencia, POS, caja y historial de cajas, inventario (importar/exportar), ventas, cuentas corrientes, usuarios, reportes, configuración. Roles: admin y cajero (el cajero no ve costos ni márgenes, solo sus ventas y su caja). Debe funcionar sin CDN (fuentes e íconos locales). La CSP prohíbe scripts y handlers en línea; hay pruebas que lo vigilan. Los ids usados por los scripts no se renombran.

## Brand Commitments
Nombre "Vortex Apex". Logo con violeta (#6246ea), carbón (#2b2c34) y un punto coral (#e45858); wordmark ancho/extendido. Se pueden mantener los colores o elegir otros que combinen con el logo.

## Evidence on Hand
Cuatro logos `.webp` en `frontend/assets/` (claro/oscuro, login/dentro del programa). No hay clientes, testimonios ni métricas para citar.

## Product Principles
1. Velocidad y claridad de cobro por encima de la decoración.
2. Funciona sin internet, siempre: nada depende de servicios externos.
3. Cada rol ve solo lo que le corresponde.
4. Una sola identidad visual en todas las pantallas.

## Accessibility & Inclusion
Uso prolongado y local con luz variable: contraste AA en claro y oscuro, navegación por teclado, foco visible, objetivos táctiles cómodos y respeto de `prefers-reduced-motion`.
