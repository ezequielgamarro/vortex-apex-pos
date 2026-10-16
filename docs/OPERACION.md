# Operación del POS (guía del proveedor)

Todo lo que sigue usa **tu llave privada** (`tools_licencia/vortex_private.key`).
Esa llave vive solo en tu PC, con backup en un lugar seguro. Si la perdés no podés
firmar más códigos; si se filtra, cualquiera puede.

## 1. Dar de alta un cliente nuevo

El programa **no trae ninguna cuenta ni contraseña por defecto**. La primera vez
que abre, muestra "Configuración inicial" con la **huella** de esa PC.

1. Instalá el programa. Al abrirlo ves la huella (`POS-XXXXXXXXXXXXXXXX-DEMO`).
   - Presencial: la leés vos. Remoto: el cliente te la manda por WhatsApp.
2. Ejecutá `tools_licencia\Generar_Alta.bat`. Pegás la huella, elegís el **rubro** y,
   si es una instalación **remota**, un **Cliente ID** (ej. `libreria-pedro`).
3. Te da un código `VXA...`. El cliente lo pega en la pantalla y elige su nombre,
   correo y contraseña. Ese usuario es el **administrador del comercio**.
4. Desde "Usuarios", el administrador crea cajeros u otros administradores.

> Con **Cliente ID** la huella **cambia** (depende de él). Después del alta pedile
> la huella nueva (menú de licencia) y emití la licencia con esa.
> En presencial podés usar `configurar_cliente.py` en vez del Cliente ID del código.

El código de alta solo sirve para esa PC y solo mientras no exista ningún usuario.

## 2. Licencia mensual

1. El cliente te manda su huella (pantalla de licencia).
2. `tools_licencia\Generar_Licencia.bat`: huella, vencimiento y días de gracia.
   El formato por defecto es **VX2** (lleva número de serie).
3. El cliente pega el código en la pantalla de licencia (solo administrador).

- **VX2** no se puede repetir: un código más viejo que el último aplicado se rechaza.
- **VX1** (formato original) sigue funcionando; elegilo solo si el cliente tiene una
  versión del POS **anterior** a esta actualización (esas no entienden VX2).
- Si falla la comprobación de licencia por un error del programa, **se deja vender**
  (decisión de negocio). Vencida la licencia, se bloquean las escrituras
  (ventas, caja, catálogo) pero se puede consultar y exportar todo.
- El vencimiento sale de la **firma** del código guardado: editar la base de datos
  no lo extiende.
- La demo de 30 días cuenta desde la primera instalación (archivo `instalacion.json`
  en la carpeta de datos). Borrar la base no la reinicia.

## 3. El cliente olvidó la contraseña

1. En el login, "¿Olvidaste tu contraseña?" muestra la huella de la PC.
2. Te la manda con su correo. Ejecutá `tools_licencia\Generar_Recuperacion.bat`.
3. Le mandás el código `VXR...` (vale 3 días, una sola vez, solo para esa PC).
4. Lo pega con una contraseña nueva. Solo sirve para cuentas de **administrador**.

Antes de enviarlo, confirmá por otro medio que quien lo pide es el dueño.

## 4. Permisos

- **Cajero**: cobra, abre/cierra **su propia caja**, ve solo **sus ventas**; no ve costos ni márgenes ni puede exportar el catálogo.
- **Administrador**: todo, incluidas las cajas y ventas de todos.

## 5. Respaldos

Al abrir el programa (máx. una vez cada ~20 h) se copia la base a
`<carpeta de datos>\backups\` (se guardan las últimas 7). **Está en la misma PC**:
pedile al cliente que copie esa carpeta a un pendrive o a la nube cada tanto.
La carpeta de datos está dentro de `%APPDATA%` y lleva el nombre de la app (a verificar
en la primera instalación real: `Punto de Venta` o `pos-escritorio`); ahí también están
`pos_local.db`, `secret.key` e `instalacion.json`.

## 6. Lector de códigos de barras

Funciona con cualquier lector USB o Bluetooth en **modo teclado** (el que viene de fábrica) que termine la lectura con **Enter** (sufijo por defecto en casi todos) o con **Tab**. No hace falta instalar nada.

- **POS:** leer un código agrega el producto al carrito, aunque el cursor no esté en el buscador. Si el código no existe, el administrador ve un acceso para crear el producto con ese código; el cajero solo ve el aviso.
- **Inventario:** leer un código abre la edición del producto, o el alta con el código ya cargado si no existe. En el alta, el cursor arranca en el campo de código y el Enter del lector no envía el formulario. Si el código ya pertenece a otro producto, aparece un aviso.
- Si el lector no agrega ningún sufijo, configuralo con el código de programación del fabricante ("sufijo Enter" / "CR").
- **Prueba con el lector real (3 pasos):** (1) en el POS, con el cursor fuera del buscador, leé un producto cargado: debe sumarse al carrito; (2) leé un código inexistente: debe avisar y, si sos administrador, ofrecer crearlo; (3) en Inventario leé el mismo código: debe abrir la edición. Si algo falla, anotá la marca y el modelo del lector.

## 7. Desarrollo

```
python -m venv app/.venv
app/.venv/Scripts/pip install -r app/requirements-dev.txt
app/.venv/Scripts/python -m pytest tests -q          # pruebas (no tocan tu base)
npm run build:backend                                  # construye dist/pos-backend.exe
npm install ; npm run dist                             # genera el instalador
```

- `ENV=development` en un `.env` habilita `/docs`. Sin `.env` el programa arranca en modo seguro.
- `ADMIN_PASSWORD` en un `.env` crea un administrador en una base **vacía** (solo para desarrollo).
- El `secret.key` de cada instalación se genera solo; no se versiona.
- No agregues `<script>` ni `onclick=` en línea al frontend: la CSP los bloquea (hay una prueba que lo vigila).

## 8. Firmar el instalador

Sin firma, Windows SmartScreen muestra "Windows protegió tu PC" al instalar. Para evitarlo
hace falta un **certificado de firma de código** (se compra, no se puede generar):

- **EV (recomendado):** el aviso desaparece desde la primera instalación. Viene en un token USB.
- **OV (estándar):** más barato; el aviso baja a medida que el instalador gana reputación.

Con el certificado en un archivo `.pfx`:

```
set CSC_LINK=C:\ruta\certificado.pfx
set CSC_KEY_PASSWORD=la-clave-del-certificado
npm run dist:firmado
```

`dist:firmado` se detiene si falta alguna de las dos variables (no genera un instalador sin
firmar sin avisar). `npm run dist` sigue generando el instalador sin firmar. La clave del
certificado va solo en variables de entorno: no la guardes en el repositorio.

## 9. Límites conocidos

- La licencia local es una **barrera comercial**, no una defensa criptográfica: la
  huella usa datos del equipo (MachineGuid de Windows, serie del volumen, BIOS) que un
  usuario con conocimientos puede falsificar, y quien borre la base **y** `instalacion.json`
  reinicia la demo. La huella cambia si se reinstala Windows, se cambia el disco o la placa:
  hay que emitir la licencia otra vez.
- El instalador **no está firmado** hasta que compres un certificado (ver sección 8).
