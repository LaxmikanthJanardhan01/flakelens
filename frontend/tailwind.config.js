/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: '#F7F8FA',
        surface: '#FFFFFF',
        border: {
          DEFAULT: '#E5E9E8',
          subtle: '#EEF2F1',
          strong: '#D1D7D6',
        },
        fl: {
          primary: '#202A32',
          secondary: '#647084',
          muted: '#8A97AA',
          teal: '#0F766E',
          'teal-hover': '#0D6860',
          'teal-bright': '#14B8A6',
          'teal-tint': '#F0FDFA',
          'teal-border': '#CCFBF1',
          success: '#159B67',
          'success-tint': '#EBF8F2',
          'success-border': '#A7E7CB',
          warning: '#D99A22',
          'warning-tint': '#FEF8EC',
          'warning-border': '#FADDA8',
          error: '#DC4B4B',
          'error-tint': '#FDF2F2',
          'error-border': '#F7BEBE',
          console: '#F1F3F7',
        },
        brand: {
          50: '#f0fdfa',
          100: '#ccfbf1',
          500: '#14b8a6',
          600: '#0f766e',
          700: '#115e59',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
      boxShadow: {
        'card': '0 1px 3px 0 rgba(0, 0, 0, 0.04), 0 1px 2px -1px rgba(0, 0, 0, 0.02)',
        'dropdown': '0 4px 6px -1px rgba(0, 0, 0, 0.07), 0 2px 4px -2px rgba(0, 0, 0, 0.05)',
        'modal': '0 10px 25px -5px rgba(0, 0, 0, 0.08), 0 8px 10px -6px rgba(0, 0, 0, 0.05)',
      }
    },
  },
  plugins: [],
}
