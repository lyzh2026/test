import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: '#0f1117',
          50: 'rgba(107, 140, 255, 0.08)',
          100: '#181b25',
          150: '#262933',
          200: '#33364a',
          300: '#6b6d7b',
        },
        brand: {
          50: '#1a1d2e',
          100: '#8ba8ff',
          200: '#7a9cff',
          300: '#6b8cff',
          400: '#5e7df0',
          500: '#5270d4',
          600: '#465db8',
          700: '#3a4d9e',
          800: '#2e3d84',
          900: '#222d6a',
        },
        text: {
          primary: '#e8e9ed',
          secondary: '#a8abb8',
          muted: '#6b6d7b',
        },
        accent: {
          green: '#4ec89e',
          red: '#e45a5a',
          amber: '#d4a84a',
          blue: '#6b8cff',
        },
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Roboto Mono', 'Menlo', 'Courier New', 'monospace'],
      },
      boxShadow: {
        'border': '0 0 0 1px #262933',
        'border-hover': '0 0 0 1px #33364a',
        'card': '0 1px 2px rgba(0, 0, 0, 0.2)',
        'card-hover': '0 4px 12px rgba(0, 0, 0, 0.3)',
        'elevated': '0 8px 24px rgba(0, 0, 0, 0.4)',
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'slide-in-right': 'slideInRight 0.2s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideInRight: {
          '0%': { opacity: '0', transform: 'translateX(-4px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
      },
    },
  },
  plugins: [],
};

export default config;
