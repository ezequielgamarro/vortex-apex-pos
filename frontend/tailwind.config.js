/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./**/*.html",
    "./**/*.{js,jsx}",
    "!./node_modules/**/*",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // ==============================================================
        // TOKENS SEMÁNTICOS DEL DESIGN SYSTEM (light/dark vía CSS vars)
        // --------------------------------------------------------------
        // Cada token `pos-*` apunta a una variable CSS (`--pos-*`).
        // El valor de esas variables se define en `css/tailwind.css`:
        //   - `:root`  -> tema claro (valores originales).
        //   - `.dark`  -> tema oscuro (sobre-escritura).
        // Resultado: TODA la app cambia de tema sin editar una sola
        // clase utilitaria en el HTML (DRY, un único punto de verdad).
        // `rgb(var(--x) / <alpha-value>)` habilita la opacidad de Tailwind
        // (p. ej. bg-pos-secondary/40) sobre variables CSS.
        // ==============================================================
        'pos-bg':         'rgb(var(--pos-bg) / <alpha-value>)',
        'pos-text-head':  'rgb(var(--pos-text-head) / <alpha-value>)',
        'pos-text-body':  'rgb(var(--pos-text-body) / <alpha-value>)',
        'pos-primary':    'rgb(var(--pos-primary) / <alpha-value>)',
        'pos-primary-text': 'rgb(var(--pos-primary-text) / <alpha-value>)',
        'pos-secondary':  'rgb(var(--pos-secondary) / <alpha-value>)',
        'pos-stroke':     'rgb(var(--pos-stroke) / <alpha-value>)',
        'pos-danger':     'rgb(var(--pos-danger) / <alpha-value>)',
        // Éxito (verde): confirmaciones de cobro y notificaciones OK.
        'pos-success':    'rgb(var(--pos-success) / <alpha-value>)',
        // Overlay/backdrop de modales y sidebar (permanece oscuro en ambos temas).
        'pos-overlay':    'rgb(var(--pos-overlay) / <alpha-value>)',
      },
      fontFamily: {
        base: ['"Jost"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        'pos-card': '0 1px 3px 0 rgba(43,44,52,0.10), 0 1px 2px -1px rgba(43,44,52,0.10)',
        'pos-primary': '0 10px 15px -3px rgba(98,70,234,0.35), 0 4px 6px -4px rgba(98,70,234,0.35)',
      },
      // Animaciones utilitarias del design system (usadas por el modal
      // "Venta Completada" y los toasts de ui.js/pos.js). Definirlas aquí las
      // compila como `animate-pop-in` / `animate-toast-in` (mecanismo oficial
      // de Tailwind: `theme.extend.animation` + `keyframes`).
      keyframes: {
        'pop-in': {
          '0%': { opacity: '0', transform: 'scale(0.94)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        'toast-in': {
          '0%': { opacity: '0', transform: 'translateY(0.75rem)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'pop-in': 'pop-in 0.18s ease-out',
        'toast-in': 'toast-in 0.2s ease-out',
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
  ],
}
