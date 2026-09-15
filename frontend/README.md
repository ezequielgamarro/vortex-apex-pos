# Frontend del Punto de Venta (POS)

Interfaz web construida con **Tailwind CSS** sobre la estructura base del template
**TailDash v1.0**, adaptada con un design system propio basado en tokens semánticos
`pos-*` y mapeada 1:1 con el backend FastAPI/Supabase.

## ⚙️ Requisitos

- **Node.js 18+** y **npm** (para compilar el CSS de Tailwind).

## 🧱 Instalación y compilación

```bash
cd frontend
npm install            # instala Tailwind + plugins
npm run build:css      # genera dist/css/app.css (minificado)
```

Para desarrollo con recarga automática del CSS:

```bash
npm run watch:css
```

> El archivo compilado `dist/css/app.css` ya se genera incluyendo la paleta `pos-*`.
> Cada HTML referencia este CSS: `<link href="./dist/css/app.css" rel="stylesheet">`.

## 🗂 Estructura

```
frontend/
├── tailwind.config.js        # Design system (paleta pos-*, tipografía, sombras)
├── postcss.config.js
├── package.json
├── css/tailwind.css          # Capa components (btn-primary, pos-card, etc.)
├── dist/css/app.css          # CSS compilado (generado)
├── assets/logo.png           # Asset del cliente (ruta pública /assets/logo.png)
├── components/
│   ├── layout.html           # Sidebar + Header + Content (layout principal)
│   ├── buttons.html          # Botones reutilizables
│   ├── inputs.html           # Inputs / campos reutilizables
│   ├── cards.html            # Tarjetas / KPIs reutilizables
│   └── modals.html           # Modales reutilizables
├── services/
│   ├── api.js                # Capa de red + interceptor JWT
│   ├── config.js             # Configuración de Supabase (login)
│   ├── login.js              # Lógica de autenticación
│   ├── dashboard.js          # Lógica de KPIs / reportes
│   ├── pos.js                # Lógica del Terminal POS
│   ├── inventario.js         # Lógica de CRUD de productos
│   └── caja.js               # Lógica de arqueo
└── *.html                    # 5 vistas (login, dashboard, pos, inventario, caja)
```

## 🖼 Vistas requeridas (mapeo 1:1 con el backend)

| Vista            | Archivo          | Backend                     |
|------------------|------------------|-----------------------------|
| Auth/Login       | `login.html`     | Supabase Auth + `/auth/perfil` |
| Dashboard        | `dashboard.html` | `/reportes/*`, `/ventas`    |
| Terminal POS     | `pos.html`       | `/productos`, `/ventas`     |
| Inventario (CRUD)| `inventario.html`| `/productos` (admin)        |
| Caja / Arqueo    | `caja.html`      | `/arqueo/*`                 |

## 🎨 Design System (tokens pos-*)

Configurado en `tailwind.config.js`:

| Token             | Hex       | Uso                            |
|-------------------|-----------|--------------------------------|
| `pos-bg`          | `#fffffe` | Fondo general de la interfaz   |
| `pos-text-head`   | `#2b2c34` | Títulos y texto principal      |
| `pos-text-body`   | `#2b2c34` | Texto de contenido             |
| `pos-primary`     | `#6246ea` | Color de acento / acciones     |
| `pos-primary-text`| `#fffffe` | Texto sobre el primario        |
| `pos-secondary`   | `#d1d1e9` | Fondos de tarjetas KPI         |
| `pos-stroke`      | `#2b2c34` | Bordes / trazos                |
| `pos-danger`      | `#e45858` | Acciones destructivas          |

> ⚠️ Prohibido usar valores hexadecimales estáticos en las clases HTML:
> siempre se usa la clase de Tailwind (p. ej. `bg-pos-primary text-pos-primary-text`).

## 🔐 Capa de red (`services/api.js`)

- Base URL: `/api` (ajustar en `const API_BASE` si el backend corre en otro host).
- Inyecta automáticamente `Authorization: Bearer <token>` desde `localStorage.getItem('token')`.
- Devuelve `401` → limpia el token y redirige a `login.html`.
- Expone la API tipada `api.*` mapeada 1:1 con los routers del backend.

## 📌 Cómo servir

Con un servidor estático simple (por ejemplo, Python o `npx serve`):

```bash
# desde frontend/
npx serve .
# o
python -m http.server 8081
```

Luego abrir `http://localhost:8081/login.html`.

> En producción, el `dist/css/app.css` se sirve junto a los HTML estáticos,
> y el backend FastAPI puede apuntar a estos ficheros como contenido estático.
