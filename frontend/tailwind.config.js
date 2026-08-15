/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        fleet: {
          ink: '#0f172a',
          muted: '#64748b',
          line: '#dbe4f0',
          bg: '#f5f7fb',
          blue: '#1d4ed8',
          navy: '#173b8f',
          cyan: '#0284c7',
          green: '#16a34a',
          amber: '#f59e0b',
          red: '#dc2626',
        },
      },
      boxShadow: {
        card: '0 12px 30px rgba(15, 23, 42, 0.08)',
        soft: '0 8px 20px rgba(29, 78, 216, 0.12)',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
