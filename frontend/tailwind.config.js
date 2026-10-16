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
        'pos-brand':      'rgb(var(--pos-brand) / <alpha-value>)',
        'pos-on-brand':   'rgb(var(--pos-on-brand) / <alpha-value>)',
        'pos-card':       'rgb(var(--pos-card) / <alpha-value>)',
        'pos-input':      'rgb(var(--pos-input) / <alpha-value>)',
        'pos-warning':    'rgb(var(--pos-warning) / <alpha-value>)',
        'pos-rail':       'rgb(var(--pos-rail) / <alpha-value>)',
        'pos-rail-text':  'rgb(var(--pos-rail-text) / <alpha-value>)',
      },
      fontFamily: {
        base: ['"Onest"', 'ui-sans-serif', 'system-ui', 'Segoe UI', 'sans-serif'],
        marca: ['"Unbounded"', '"Onest"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        'pos-card': '0 1px 2px rgb(var(--pos-shadow) / 0.05), 0 8px 24px -12px rgb(var(--pos-shadow) / var(--pos-shadow-a))',
        'pos-primary': '0 10px 24px -10px rgb(0 0 0 / 0.4)',
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
