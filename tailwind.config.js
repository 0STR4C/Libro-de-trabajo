/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    './frontend/**/*.{js,jsx,ts,tsx}',
    './app/static/**/*.{html,js}'
  ],
  prefix: 'tw-',
  important: '#prime-react-root',
  corePlugins: {
    preflight: false
  },
  theme: {
    extend: {}
  },
  plugins: []
};
