/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    './frontend/**/*.{js,jsx,ts,tsx}',
    './app/static/**/*.{html,js}'
  ],
  prefix: 'tw-',
  // Las ventanas PrimeReact se portan a body; el prefijo tw- aísla las utilidades allí también.
  important: true,
  corePlugins: {
    preflight: false
  },
  theme: {
    extend: {
      colors: {
        'app-canvas': 'var(--bg)',
        'app-surface': 'var(--surface)',
        'app-text': 'var(--text)',
        'app-muted': 'var(--text-muted)',
        'app-border': 'var(--border)',
        'app-primary': 'var(--color-primary)'
      },
      boxShadow: { 'app-card': 'var(--shadow-card)' }
    }
  },
  plugins: []
};
