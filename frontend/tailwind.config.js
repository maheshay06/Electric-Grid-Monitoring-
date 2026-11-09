/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        navy: { 950: '#0B1020', 900: '#141B3A', 800: '#1E2752', 700: '#2D3A7C', 600: '#4452A8' },
        brand: { DEFAULT: '#6366F1', light: '#E0E7FF', dark: '#4338CA' },
        accent: { DEFAULT: '#06B6D4', light: '#CFFAFE' },
        surface: '#F3F5FB',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(20,27,58,.05), 0 10px 30px -8px rgba(67,56,202,.12)',
      },
    },
  },
  plugins: [],
};
